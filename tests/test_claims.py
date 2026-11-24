"""Tests for skills/record-claim/scripts/claims.py.

Standard library only, like the script:

    python3 -m unittest discover -s tests

Each test builds a throwaway git repository with a ledger in it, and drives
the script through `main()` exactly as an agent would through the shell.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "record-claim" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import claims  # noqa: E402


def run(root: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = claims.main(["--root", str(root), *args])
    return code, out.getvalue(), err.getvalue()


class LedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git = ["git", "-C", str(self.repo)]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "config", "user.email", "t@example.org"], check=True)
        subprocess.run([*git, "config", "user.name", "t"], check=True)
        (self.repo / "sim.py").write_text("print(31.1)\n")
        subprocess.run([*git, "add", "."], check=True)
        subprocess.run([*git, "commit", "-qm", "sim"], check=True)
        self.commit = subprocess.run(
            [*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        self.root = self.repo / "claims"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # --- helpers ---------------------------------------------------------------

    def draft(self, title: str, statement: str, reasoning: str, **fields) -> str:
        code, out, _ = run(self.root, "new", title, "--type", "result")
        self.assertEqual(code, 0)
        cid = out.splitlines()[0]
        folder = self.root / cid
        (folder / "evidence" / "01-reasoning.md").write_text(reasoning)
        (folder / "evidence" / "02-output.txt").write_text("residual 31.1 um\n")
        claim = json.loads((folder / "claim.json").read_text())
        claim.update(
            statement=statement,
            holds_when="Simulation, linear ramp.",
            provenance={"commit": self.commit},
        )
        claim["evidence"].append(
            {"kind": "output", "file": "evidence/02-output.txt", "caption": "Run log"}
        )
        claim.update(fields)
        (folder / "claim.json").write_text(json.dumps(claim, indent=2))
        return cid

    def load(self, cid: str) -> dict:
        return json.loads((self.root / cid / "claim.json").read_text())

    def save(self, claim: dict) -> None:
        (self.root / claim["id"] / "claim.json").write_text(json.dumps(claim, indent=2))

    # --- tests -------------------------------------------------------------------

    def test_new_starts_a_draft_named_by_date_and_title(self) -> None:
        code, out, _ = run(self.root, "new", "RK4 reproduces the resonance curve")
        self.assertEqual(code, 0)
        cid = out.splitlines()[0]
        self.assertRegex(cid, r"^\d{4}-\d{2}-\d{2}-rk4-reproduces-the-resonance-curve$")
        self.assertEqual(self.load(cid)["status"], "draft")
        # A second with the same title gets its own id.
        _, out2, _ = run(self.root, "new", "RK4 reproduces the resonance curve")
        self.assertTrue(out2.splitlines()[0].endswith("-2"))

    def test_a_complete_claim_seals_and_then_checks_clean(self) -> None:
        cid = self.draft("Residual", "The residual is 31.1 um.", "Read off the log.")
        code, out, _ = run(self.root, "seal", cid)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.load(cid)["status"], "sealed")
        code, out, _ = run(self.root, "check")
        self.assertEqual(code, 0, out)

    def test_a_sealed_claim_that_changes_fails_check(self) -> None:
        cid = self.draft("Residual", "The residual is 31.1 um.", "Read off the log.")
        run(self.root, "seal", cid)
        (self.root / cid / "evidence" / "02-output.txt").write_text("residual 3.11 um\n")
        code, out, _ = run(self.root, "check", cid)
        self.assertEqual(code, 1)
        self.assertIn("changed after it was sealed", out)

    def test_editing_the_statement_after_sealing_also_breaks_the_seal(self) -> None:
        cid = self.draft("Residual", "The residual is 31.1 um.", "Read off the log.")
        run(self.root, "seal", cid)
        claim = self.load(cid)
        claim["statement"] = "The residual is small."
        self.save(claim)
        code, out, _ = run(self.root, "check", cid)
        self.assertEqual(code, 1)
        self.assertIn("changed after it was sealed", out)

    def test_recording_the_library_id_does_not_break_the_seal(self) -> None:
        cid = self.draft("Residual", "The residual is 31.1 um.", "Read off the log.")
        run(self.root, "seal", cid)
        lib = "0d014a26-3904-444a-b99b-6d40988c18a2"
        self.assertEqual(run(self.root, "published", cid, lib)[0], 0)
        self.assertEqual(self.load(cid)["library"]["id"], lib)
        self.assertEqual(run(self.root, "check", cid)[0], 0)

    def test_a_draft_with_errors_is_not_sealed(self) -> None:
        cid = self.draft("Residual", "", "Read off the log.")
        code, out, _ = run(self.root, "seal", cid)
        self.assertEqual(code, 1)
        self.assertIn("statement is missing", out)
        self.assertEqual(self.load(cid)["status"], "draft")

    def test_a_number_not_in_the_evidence_is_flagged(self) -> None:
        cid = self.draft("Residual", "The residual is 0.009 um.", "Read off the log.")
        _, out, _ = run(self.root, "check", cid)
        self.assertIn("found in no evidence item: 0.009", out)

    def test_a_sealed_claim_cannot_rest_on_a_draft(self) -> None:
        base = self.draft("Base", "The residual is 31.1 um.", "Log.")
        top = self.draft(
            "Top",
            "Smaller than the residual of 31.1 um.",
            "Compared with the base claim.",
            citations=[{"local": base, "relation": "uses", "reason": "the baseline"}],
        )
        code, out, _ = run(self.root, "seal", top)
        self.assertEqual(code, 1)
        self.assertIn("still a draft", out)
        run(self.root, "seal", base)
        self.assertEqual(run(self.root, "seal", top)[0], 0)

    def test_citations_in_a_circle_are_an_error(self) -> None:
        a = self.draft("A", "The residual is 31.1 um.", "Log.")
        b = self.draft(
            "B", "The residual is 31.1 um.", "Log.",
            citations=[{"local": a, "relation": "uses", "reason": "x"}],
        )
        claim = self.load(a)
        claim["citations"] = [{"local": b, "relation": "uses", "reason": "x"}]
        self.save(claim)
        _, out, _ = run(self.root, "check")
        self.assertIn("citations go in a circle", out)

    def test_an_unknown_local_citation_is_an_error(self) -> None:
        cid = self.draft(
            "A", "The residual is 31.1 um.", "Log.",
            citations=[{"local": "2020-01-01-nothing", "reason": "x"}],
        )
        _, out, _ = run(self.root, "check", cid)
        self.assertIn("no claim '2020-01-01-nothing' in this ledger", out)

    def test_trace_walks_back_to_the_outside_sources(self) -> None:
        base = self.draft(
            "Base", "The residual is 31.1 um.", "Log.",
            citations=[{"external": "arxiv:2101.00001", "relation": "uses", "reason": "the model"}],
        )
        top = self.draft(
            "Top", "The residual is 31.1 um.", "Log.",
            citations=[{"local": base, "relation": "extends", "reason": "refines it"}],
        )
        code, out, _ = run(self.root, "trace", top)
        self.assertEqual(code, 0)
        self.assertIn(f"extends {base}", out)
        self.assertIn("uses arxiv:2101.00001 — the model", out)

    def test_payload_is_private_and_waits_for_cited_claims(self) -> None:
        base = self.draft("Base", "The residual is 31.1 um.", "Log.")
        top = self.draft(
            "Top", "The residual is 31.1 um.", "As in claim [1].",
            citations=[{"local": base, "relation": "uses", "reason": "the baseline"}],
        )
        run(self.root, "seal", base)
        run(self.root, "seal", top)
        code, _, err = run(self.root, "payload", top)
        self.assertEqual(code, 2)
        self.assertIn(f"Publish in this order: {base} {top}", err)

        lib = "11111111-2222-3333-4444-555555555555"
        run(self.root, "published", base, lib)
        code, out, _ = run(self.root, "payload", top)
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertIs(payload["private"], True)
        self.assertEqual(payload["citations"][0]["claim_id"], lib)
        self.assertEqual(payload["evidence"][0]["content"], "As in claim [1].")
        self.assertIn(f"ledger:{top}", payload["anchors"])
        self.assertEqual(payload["provenance"]["ledger_id"], top)

    def test_a_local_only_item_stays_out_of_the_payload(self) -> None:
        cid = self.draft("A", "The residual is 31.1 um.", "Log.")
        folder = self.root / cid
        (folder / "evidence" / "03-output.txt").write_text("x" * 20000 + "\n31.1\n")
        claim = self.load(cid)
        claim["evidence"].append({"kind": "output", "file": "evidence/03-output.txt"})
        self.save(claim)
        _, out, _ = run(self.root, "check", cid)
        self.assertIn("Mark it \"local_only\": true", out)

        claim["evidence"][-1]["local_only"] = True
        self.save(claim)
        _, out, _ = run(self.root, "check", cid)
        self.assertNotIn("local_only", out)
        run(self.root, "seal", cid)
        payload = json.loads(run(self.root, "payload", cid)[1])
        self.assertEqual(len(payload["evidence"]), 2)  # reasoning and the short log

    def test_an_evidence_file_git_ignores_is_an_error(self) -> None:
        (self.repo / ".gitignore").write_text("*.txt\n")
        cid = self.draft("A", "The residual is 31.1 um.", "Log.")
        code, out, _ = run(self.root, "check", cid)
        self.assertEqual(code, 1)
        self.assertIn("evidence/02-output.txt is ignored by git ('*.txt' in .gitignore:1)", out)
        self.assertIn("!claims/**", out)
        # Nor can it be sealed that way.
        self.assertEqual(run(self.root, "seal", cid)[0], 1)

        (self.repo / ".gitignore").write_text("*.txt\n!claims/**\n")
        self.assertEqual(run(self.root, "check", cid)[0], 0)

    def test_a_file_already_committed_is_not_reported(self) -> None:
        cid = self.draft("A", "The residual is 31.1 um.", "Log.")
        subprocess.run(["git", "-C", str(self.repo), "add", "claims"], check=True)
        (self.repo / ".gitignore").write_text("*.txt\n")
        self.assertEqual(run(self.root, "check", cid)[0], 0)

    def test_index_warns_about_ignored_files(self) -> None:
        (self.repo / ".gitignore").write_text("*.txt\n")
        self.draft("A", "The residual is 31.1 um.", "Log.")
        code, _, err = run(self.root, "index")
        self.assertEqual(code, 0)
        self.assertIn("is ignored by git", err)

    def test_new_takes_the_date_of_the_finding(self) -> None:
        code, out, _ = run(self.root, "new", "Linear ramp residual", "--date", "2026-10-08")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], "2026-10-08-linear-ramp-residual")
        self.assertEqual(run(self.root, "new", "x", "--date", "8.10.2026")[0], 2)
        self.assertEqual(run(self.root, "new", "x", "--date", "2999-01-01")[0], 2)

    def test_payload_refuses_a_draft(self) -> None:
        cid = self.draft("A", "The residual is 31.1 um.", "Log.")
        code, _, err = run(self.root, "payload", cid)
        self.assertEqual(code, 2)
        self.assertIn("seal it before publishing", err)

    def test_index_lists_claims_and_draws_the_graph(self) -> None:
        base = self.draft("Base", "The residual is 31.1 um.", "Log.")
        self.draft(
            "Top", "The residual is 31.1 um.", "Log.",
            citations=[{"local": base, "relation": "uses", "reason": "x"}],
        )
        self.assertEqual(run(self.root, "index")[0], 0)
        readme = (self.root / "README.md").read_text()
        self.assertIn(f"[{base}]({base}/claim.json)", readme)
        self.assertIn("```mermaid", readme)
        self.assertIn("-- uses -->", readme)

    # --- conventions ---------------------------------------------------------------

    def test_a_seal_made_before_conventions_existed_still_verifies(self) -> None:
        """The seal of a claim without conventions or reviews is computed
        exactly as before they existed, so no old ledger breaks."""
        cid = self.draft("Residual", "The residual is 31.1 um.", "Read off the log.")
        claim = self.load(cid)
        claim.pop("conventions", None)
        self.save(claim)
        core = {k: claim.get(k) for k in claims.CORE_FIELDS}
        h = claims.hashlib.sha256(
            json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")
        )
        for item in claim["evidence"]:
            data = (self.root / cid / item["file"]).read_bytes()
            h.update(item["file"].encode() + b"\0" + claims.sha256(data).encode())
        ledger = claims.Ledger(self.root)
        self.assertEqual(claims.seal_of(ledger, claim), h.hexdigest())

    def test_conventions_are_versioned_and_a_claim_names_one_version(self) -> None:
        self.assertEqual(
            run(self.root, "conv", "add", "psd-one-sided", "S is one-sided.",
                "--category", "normalisation")[1].strip(),
            "psd-one-sided@1",
        )
        self.assertEqual(run(self.root, "conv", "add", "psd-one-sided", "x")[0], 2)
        cid = self.draft(
            "Residual", "The residual is 31.1 um.", "Log.",
            conventions=["psd-one-sided@1"],
        )
        self.assertEqual(run(self.root, "check", cid)[0], 0)
        run(self.root, "conv", "revise", "psd-one-sided", "S is two-sided.",
            "--why", "matches the lab's analyser")
        _, out, _ = run(self.root, "check", cid)
        self.assertIn("the project now uses psd-one-sided@2", out)
        _, out, _ = run(self.root, "conv", "show", "psd-one-sided")
        self.assertIn(f"used by {cid}", out)

        bad = self.draft("Bad", "The residual is 31.1 um.", "Log.",
                         conventions=["psd-one-sided@7", "nonsense"])
        _, out, _ = run(self.root, "check", bad)
        self.assertIn("psd-one-sided@7 is not in conventions.json", out)
        self.assertIn("is not 'key@version'", out)

    def test_rewording_a_convention_breaks_the_seal_of_a_claim_written_in_it(self) -> None:
        run(self.root, "conv", "add", "units", "Lengths in um.")
        cid = self.draft("Residual", "The residual is 31.1 um.", "Log.",
                         conventions=["units@1"])
        self.assertEqual(run(self.root, "seal", cid)[0], 0)
        data = json.loads((self.root / "conventions.json").read_text())
        data["conventions"][0]["versions"][0]["statement"] = "Lengths in mm."
        (self.root / "conventions.json").write_text(json.dumps(data))
        code, out, _ = run(self.root, "check", cid)
        self.assertEqual(code, 1)
        self.assertIn("changed after it was sealed", out)

    def test_numbers_without_conventions_are_questioned_once_conventions_exist(self) -> None:
        cid = self.draft("Residual", "The residual is 31.1 um.", "Log.")
        _, out, _ = run(self.root, "check", cid)
        self.assertNotIn("names no convention", out)
        run(self.root, "conv", "add", "units", "Lengths in um.")
        _, out, _ = run(self.root, "check", cid)
        self.assertIn("names no convention", out)

    def test_the_payload_carries_the_conventions_in_full(self) -> None:
        run(self.root, "conv", "add", "units", "Lengths in um.", "--category", "units")
        cid = self.draft("Residual", "The residual is 31.1 um.", "Log.",
                         conventions=["units@1"])
        run(self.root, "seal", cid)
        payload = json.loads(run(self.root, "payload", cid)[1])
        self.assertEqual(
            payload["conventions"],
            [{"key": "units", "version": 1, "statement": "Lengths in um.", "category": "units"}],
        )

    # --- reviews of papers ----------------------------------------------------------

    def review(self, source: str, locator: str, **fields) -> str:
        code, out, err = run(self.root, "source", "new", source, "--locator", locator)
        self.assertEqual(code, 0, err)
        rel = out.strip()
        data = json.loads((self.root / rel).read_text())
        data.update(
            read_from="latex",
            verdict="holds",
            quote=r"\omega = \sqrt{k/m}",
            purpose="The trap frequency.",
            summary="Re-derived; it holds.",
        )
        data.update(fields)
        (self.root / rel).write_text(json.dumps(data, indent=2))
        return rel

    def test_a_review_is_filed_under_the_paper_whatever_its_spelling(self) -> None:
        rel = self.review("https://arxiv.org/abs/2502.09437v2", "Eq. (12)")
        self.assertTrue(rel.startswith("sources/arxiv-2502.09437/"), rel)
        data = json.loads((self.root / rel).read_text())
        self.assertEqual((data["source"], data["source_version"]), ("arxiv:2502.09437", "v2"))
        self.assertEqual(run(self.root, "check", rel)[0], 0)

    def test_nothing_read_is_nothing_judged(self) -> None:
        rel = self.review("arxiv:2502.09437", "Eq. (12)", read_from="none", verdict="holds")
        code, out, _ = run(self.root, "check", rel)
        self.assertEqual(code, 1)
        self.assertIn("the verdict is 'could_not_check'", out)

    def test_a_version_longer_than_the_library_takes_is_an_error(self) -> None:
        rel = self.review("arxiv:2502.09437", "Eq. (12)", source_version="v" * 65)
        code, out, _ = run(self.root, "check", rel)
        self.assertEqual(code, 1)
        self.assertIn("source_version is longer than 64", out)

    def test_a_paper_kept_in_the_ledger_is_questioned(self) -> None:
        rel = self.review("arxiv:2502.09437", "Eq. (12)")
        (self.root / rel).parent.joinpath("paper.pdf").write_bytes(b"%PDF")
        _, out, _ = run(self.root, "check")
        self.assertIn("paper.pdf: not a review: papers go in .berry/papers/", out)

    def test_using_a_paper_without_a_review_is_questioned(self) -> None:
        cid = self.draft(
            "A", "The residual is 31.1 um.", "Log.",
            citations=[{"external": "arxiv:2502.09437", "relation": "uses", "reason": "x"}],
        )
        _, out, _ = run(self.root, "check", cid)
        self.assertIn("say where (locator", out)
        self.assertIn("no source review of that passage", out)

    def test_building_on_a_passage_found_wrong_is_an_error(self) -> None:
        rel = self.review("arxiv:2502.09437", "Eq. (12)", verdict="fails")
        cid = self.draft(
            "A", "The residual is 31.1 um.", "Log.",
            citations=[{"external": "arxiv:2502.09437v1", "relation": "uses",
                        "locator": "Eq. (12)", "review": rel, "reason": "x"}],
        )
        code, out, _ = run(self.root, "check", cid)
        self.assertEqual(code, 1)
        self.assertIn("uses a passage its review found wrong", out)

    def test_a_review_of_another_paper_is_an_error(self) -> None:
        rel = self.review("arxiv:2502.09437", "Eq. (12)")
        cid = self.draft(
            "A", "The residual is 31.1 um.", "Log.",
            citations=[{"external": "arxiv:1111.11111", "relation": "uses",
                        "locator": "Eq. (12)", "review": rel, "reason": "x"}],
        )
        _, out, _ = run(self.root, "check", cid)
        self.assertIn("its review is of arxiv:2502.09437", out)

    def test_changing_a_cited_review_breaks_the_seal_but_publishing_it_does_not(self) -> None:
        rel = self.review("arxiv:2502.09437", "Eq. (12)")
        cid = self.draft(
            "A", "The residual is 31.1 um.", "Log.",
            citations=[{"external": "arxiv:2502.09437", "relation": "uses",
                        "locator": "Eq. (12)", "review": rel, "reason": "x"}],
        )
        self.assertEqual(run(self.root, "seal", cid)[0], 0)
        lib = "22222222-2222-3333-4444-555555555555"
        self.assertEqual(run(self.root, "source", "published", rel, lib)[0], 0)
        self.assertEqual(run(self.root, "check", cid)[0], 0)
        data = json.loads((self.root / rel).read_text())
        data["verdict"] = "fails"
        (self.root / rel).write_text(json.dumps(data))
        _, out, _ = run(self.root, "check", cid)
        self.assertIn("changed after it was sealed", out)

    def test_publishing_order_is_correction_then_review_then_claim(self) -> None:
        run(self.root, "conv", "add", "units", "Lengths in um.")
        fix = self.draft("Corrected Eq. 12", "The residual is 31.1 um.", "Log.",
                         conventions=["units@1"])
        rel = self.review(
            "arxiv:2502.09437", "Eq. (12)", verdict="holds_with_correction",
            correction={"local": fix},
            items=[{"body": "A factor 2 is missing.", "proposed_fix": "2 x"}],
        )
        top = self.draft(
            "Top", "The residual is 31.1 um.", "Log.",
            conventions=["units@1"],
            citations=[
                {"local": fix, "relation": "uses", "reason": "the corrected form"},
                {"external": "arxiv:2502.09437", "relation": "uses",
                 "locator": "Eq. (12)", "review": rel, "reason": "x"},
            ],
        )
        run(self.root, "seal", fix)
        self.assertEqual(run(self.root, "seal", top)[0], 0)
        _, out, _ = run(self.root, "order", top)
        self.assertEqual(out.split(), [fix, rel, top])

        code, _, err = run(self.root, "source", "payload", rel)
        self.assertEqual(code, 2)
        self.assertIn("is not in the Library yet", err)
        fix_lib = "33333333-2222-3333-4444-555555555555"
        run(self.root, "published", fix, fix_lib)
        payload = json.loads(run(self.root, "source", "payload", rel, "--public")[1])
        self.assertEqual(payload["correction_claim_id"], fix_lib)
        self.assertEqual(payload["source"], "arxiv:2502.09437")
        self.assertNotIn("private", payload)

        rev_lib = "44444444-2222-3333-4444-555555555555"
        run(self.root, "source", "published", rel, rev_lib)
        payload = json.loads(run(self.root, "payload", top)[1])
        paper = payload["citations"][1]
        self.assertEqual((paper["locator"], paper["source_review_id"]), ("Eq. (12)", rev_lib))

    def test_index_lists_conventions_and_papers_checked(self) -> None:
        run(self.root, "conv", "add", "units", "Lengths in um.")
        self.review("arxiv:2502.09437", "Eq. (12)")
        self.draft("A", "The residual is 31.1 um.", "Log.")
        run(self.root, "index")
        readme = (self.root / "README.md").read_text()
        self.assertIn("| `units@1` | Lengths in um. |", readme)
        self.assertIn("| arxiv:2502.09437 | Eq. (12) | holds |", readme)

    # --- audits ----------------------------------------------------------------------

    def chain(self) -> tuple[str, str]:
        base = self.draft("Base", "The residual is 31.1 um.", "Log.")
        top = self.draft(
            "Top", "The residual is 31.1 um.", "Log.",
            citations=[{"local": base, "relation": "uses", "reason": "x"}],
        )
        run(self.root, "seal", base)
        run(self.root, "seal", top)
        return base, top

    def status(self, *ids: str) -> str:
        return run(self.root, "audit-status", "--all", *ids)[1]

    def test_an_audited_claim_is_not_checked_again(self) -> None:
        base, top = self.chain()
        self.assertIn(f"never   {top}", self.status())
        code, out, _ = run(self.root, "audit", top, "--clean", "--agent", "test")
        self.assertEqual(code, 0, out)
        self.assertIn(f"current {top}", self.status())
        # The default listing shows only what needs checking.
        _, out, _ = run(self.root, "audit-status")
        self.assertNotIn(top, out)
        self.assertIn(base, out)

    def test_a_change_below_makes_the_audit_stale_and_says_what(self) -> None:
        base, top = self.chain()
        run(self.root, "audit", top, "--clean", "--agent", "test")
        claim = self.load(base)
        claim["seal"]["sha256"] = "0" * 64  # as if base had been re-sealed
        self.save(claim)
        out = self.status(top)
        self.assertIn(f"STALE   {top}", out)
        self.assertIn(f"{base}, which it rests on, changed", out)

    def test_a_new_refutation_makes_the_audit_stale(self) -> None:
        base, top = self.chain()
        run(self.root, "audit", top, "--clean", "--agent", "test")
        fix = self.draft(
            "Fix", "The residual is 31.1 um.", "Log.",
            citations=[{"local": base, "relation": "refutes", "reason": "wrong"}],
        )
        self.assertIn(f"{fix} refutes it or something it rests on", self.status(top))

    def test_a_new_critical_review_of_a_paper_used_makes_it_stale(self) -> None:
        rel = self.review("arxiv:2502.09437", "Eq. (12)")
        cid = self.draft(
            "A", "The residual is 31.1 um.", "Log.",
            citations=[{"external": "arxiv:2502.09437", "relation": "uses",
                        "locator": "Eq. (12)", "review": rel, "reason": "x"}],
        )
        run(self.root, "seal", cid)
        run(self.root, "audit", cid, "--clean", "--agent", "test")
        self.assertIn(f"current {cid}", self.status(cid))
        self.review("arxiv:2502.09437", "Eq. (13)", verdict="fails")
        self.assertIn("a new review of a paper it uses found a passage wrong", self.status(cid))

    def test_findings_are_recorded_and_checked(self) -> None:
        _, top = self.chain()
        bad = self.repo / "bad.json"
        bad.write_text(json.dumps([{"severity": "huge", "text": "x"}]))
        self.assertEqual(run(self.root, "audit", top, "--findings", str(bad), "--agent", "t")[0], 2)
        good = self.repo / "good.json"
        good.write_text(json.dumps([{"severity": "moderate", "text": "Rounded wrong.",
                                     "quote": "31.1", "file": "evidence/02-output.txt"}]))
        _, out, _ = run(self.root, "audit", top, "--findings", str(good), "--agent", "t")
        self.assertIn("1 finding(s), worst moderate", out)
        saved = json.loads((self.root / "audits" / f"{top}.json").read_text())
        self.assertEqual(saved["audits"][-1]["findings"][0]["severity"], "moderate")

    def test_a_draft_is_not_audited(self) -> None:
        cid = self.draft("A", "The residual is 31.1 um.", "Log.")
        _, _, err = run(self.root, "audit", cid, "--clean", "--agent", "t")
        self.assertIn("is a draft", err)

    def test_a_pushed_commit_is_not_asked_about_again(self) -> None:
        remote = Path(self.tmp.name) / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        git = ["git", "-C", str(self.repo)]
        subprocess.run([*git, "remote", "add", "origin", str(remote)], check=True)
        subprocess.run([*git, "push", "-q", "origin", "HEAD:main"], check=True)
        subprocess.run([*git, "fetch", "-q", "origin"], check=True)
        self.assertEqual(claims.commit_state(self.repo, self.commit), "pushed")
        calls = []
        real = claims.git
        claims.git = lambda *a, **k: (calls.append(a), real(*a, **k))[1]
        try:
            self.assertEqual(claims.commit_state(self.repo, self.commit), "pushed")
        finally:
            claims.git = real
        self.assertEqual([c[0] for c in calls], ["rev-parse"])  # no cat-file, no branch

    def test_pending_lists_the_drafts_with_their_check(self) -> None:
        a = self.draft("A", "The residual is 31.1 um.", "Log.")
        b = self.draft("B", "", "Log.")
        run(self.root, "seal", a)
        _, out, _ = run(self.root, "pending")
        self.assertNotIn(a, out)
        self.assertIn(f"{b}  [1 error(s)", out)

    def test_a_standard_reference_value_needs_no_source_review(self) -> None:
        codata = {"external": "https://physics.nist.gov/cuu/Constants/", "relation": "uses",
                  "reason": "The Rb-87 mass."}
        paper = {"external": "doi:10.1103/RevModPhys.93.025010", "relation": "uses",
                 "locator": "Table XXXI", "reason": "The Rb-87 mass."}
        cid = self.draft("Residual", "The residual is 31.1 um.", "Log.", citations=[paper])
        _, out, _ = run(self.root, "check", cid)
        self.assertIn("with no source review", out)
        claim = self.load(cid)
        claim["citations"] = [{**paper, "standard": True}]
        self.save(claim)
        _, out, _ = run(self.root, "check", cid)
        self.assertNotIn("source review", out)
        claim["citations"] = [{**codata, "standard": True}]
        self.save(claim)
        _, out, _ = run(self.root, "check", cid)
        self.assertIn("say where (locator: 'CODATA 2018')", out)
        claim["citations"] = [{**paper, "standard": True, "review": "sources/x/y.json"}]
        self.save(claim)
        code, out, _ = run(self.root, "check", cid)
        self.assertEqual(code, 1)
        self.assertIn("has no review; drop one of the two", out)

    # --- what a draft rests on without saying so ------------------------------

    def test_a_draft_citing_nothing_is_asked_about_related_earlier_claims(self) -> None:
        a = self.draft(
            "Linear ramp leaves a residual oscillation of 31.1 um",
            "The linear transport ramp leaves a residual oscillation of 31.1 um.",
            "Read off the log.",
        )
        run(self.root, "seal", a)
        b = self.draft(
            "Smooth transport ramp reduces the residual oscillation",
            "A smooth transport ramp reduces the residual oscillation below 31.1 um.",
            "Compared with the log.",
        )
        _, out, _ = run(self.root, "check", b)
        self.assertIn(f"{b}: cites no earlier claim, but these share its subject: {a}", out)
        # Cited, the question is answered.
        claim = self.load(b)
        claim["citations"] = [{"local": a, "relation": "extends", "reason": "The baseline."}]
        self.save(claim)
        _, out, _ = run(self.root, "check", b)
        self.assertNotIn("cites no earlier claim", out)

    def test_a_draft_naming_a_session_round_is_questioned(self) -> None:
        cid = self.draft("Round 5 ramp", "The residual is 31.1 um.", "Log.")
        _, out, _ = run(self.root, "check", cid)
        self.assertIn("title says 'Round 5'", out)
        claim = self.load(cid)
        claim["title"] = "A round-trip ramp leaves 31.1 um"
        self.save(claim)
        _, out, _ = run(self.root, "check", cid)
        self.assertNotIn("a reader was not in the session", out)

    def test_an_unrelated_draft_is_not_asked(self) -> None:
        a = self.draft("Residual", "The residual is 31.1 um.", "Log.")
        run(self.root, "seal", a)
        b = self.draft("Detector dark counts", "Dark counts are 31.1 per second.", "Log.")
        _, out, _ = run(self.root, "check", b)
        self.assertNotIn("cites no earlier claim", out)

    def test_numbers_in_the_reasoning_must_come_from_somewhere(self) -> None:
        cid = self.draft(
            "Residual",
            "The residual is 31.1 um.",
            "With the trap frequency of 52.3 Hz from the calibration on "
            "2026-10-01, the log gives 31.1 um.",
        )
        _, out, _ = run(self.root, "check", cid)
        self.assertIn("numbers in the reasoning found in no other evidence item", out)
        self.assertIn("52.3", out)
        self.assertNotIn("2026", out.split("numbers in the reasoning")[1].split("\n")[0])
        # Once a cited claim carries it, it is sourced.
        cal = self.draft("Trap frequency is 52.3 Hz", "The trap frequency is 52.3 Hz.", "Fit.")
        claim = self.load(cid)
        claim["citations"] = [{"local": cal, "relation": "uses", "reason": "Trap frequency."}]
        self.save(claim)
        _, out, _ = run(self.root, "check", cid)
        self.assertNotIn("numbers in the reasoning", out)

    def test_sealed_claims_are_not_asked_again(self) -> None:
        cid = self.draft("Residual", "The residual is 31.1 um.", "Uses 52.3 Hz.")
        run(self.root, "seal", cid)
        _, out, _ = run(self.root, "check", cid)
        self.assertNotIn("numbers in the reasoning", out)


class LibraryUrlTest(unittest.TestCase):
    def test_berry_science_unless_berry_web_url_is_set(self) -> None:
        from unittest import mock

        with mock.patch.dict("os.environ", {}, clear=False) as env:
            env.pop("BERRY_WEB_URL", None)
            self.assertEqual(claims.library_url(), "https://berry.science/library")
        with mock.patch.dict("os.environ", {"BERRY_WEB_URL": "http://127.0.0.1:3001/"}):
            self.assertEqual(claims.library_url(), "http://127.0.0.1:3001/library")


if __name__ == "__main__":
    unittest.main()

