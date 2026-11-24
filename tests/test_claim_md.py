"""Tests for claim.md, the short form of a claim, in claims.py.

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "claims" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import claims  # noqa: E402


def run(root: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = claims.main(["--root", str(root), *args])
    return code, out.getvalue(), err.getvalue()


GOOD = """\
---
title: Simulated STA-type ramp removes the residual CoM oscillation (31.1 → 0.009 µm)
statement: In the simulated transport, the STA-type ramp reduces the residual
  CoM oscillation from 31.1 µm to 0.009 µm.
type: result
holds_when: Simulation (transport_sim). y_coil ramped -5.5063 → -1.5318 A.
conventions: lengths-um@1
command: python sim.py --ramp sta
contributors: Claude Code (claude-opus-5-5), NumPy 2.1
---

The log [2] shows 0.009 µm after the hold, against 31.1 µm before [1].

<!-- a note to self,
over two lines -->
```
## Evidence  (inside a fence: still reasoning)
```

## Evidence
- output: runs/sta.log — Run log, verbatim.
- runs/com.vl.json — CoM position during the hold.
- parameters: `runs/my params.json` local-only

## Cites
- extends 2026-10-08-linear-ramp-residual — The residual this claim removes.
- uses commit — The code that produced every number here.
- uses doi:10.1103/RevModPhys.91.045001 at "Eq. (34)" review claims/sources/doi-10.1103-revmodphys.91.045001/2026-10-09-eq-34.json — The ramp
  shape.
- uses doi:10.1103/RevModPhys.88.035009 at "CODATA 2018" standard -- The mass.
"""


class ParseTest(unittest.TestCase):
    def test_a_good_file(self) -> None:
        parsed, errors = claims.parse_claim_md(GOOD)
        self.assertEqual(errors, [])
        h = {k: v for k, (v, _) in parsed["header"].items()}
        self.assertTrue(h["statement"].endswith("from 31.1 µm to 0.009 µm."))
        self.assertIn("CoM oscillation", h["statement"])  # the continuation line
        self.assertEqual(h["claim_type"], "result")
        self.assertEqual(h["contributors"], ["Claude Code (claude-opus-5-5)", "NumPy 2.1"])
        self.assertEqual(h["conventions"], ["lengths-um@1"])
        self.assertNotIn("note to self", parsed["reasoning"])
        self.assertIn("## Evidence  (inside a fence", parsed["reasoning"])
        ev = parsed["evidence"]
        self.assertEqual([e["kind"] for e in ev], ["output", "figure", "parameters"])
        self.assertEqual(ev[2]["path"], "runs/my params.json")
        self.assertTrue(ev[2]["local_only"])
        self.assertIsNone(ev[2]["caption"])
        cites = parsed["cites"]
        self.assertEqual(cites[0]["local"], "2026-10-08-linear-ramp-residual")
        self.assertTrue(cites[1]["commit"])
        self.assertEqual(cites[2]["locator"], "Eq. (34)")
        self.assertEqual(cites[2]["reason"], "The ramp shape.")
        self.assertTrue(cites[3]["standard"])
        self.assertEqual(cites[3]["reason"], "The mass.")

    def test_each_error_names_its_line(self) -> None:
        head = "---\ntitle: T\n---\nBody.\n"
        cases = [
            ("title: T\n", 1, "starts with a header"),
            ("---\ntitle: T\nBody.\n", 1, "never closed"),
            ("---\ntitle: T\nstatment: S\n---\n", 3, "unknown key 'statment'"),
            ("---\ntitle: T\ntitle: U\n---\n", 3, "given twice (first on line 2)"),
            ('---\ntitle: "T"\n---\n', 2, "drop the quotes"),
            ("---\ntype: results\n---\n", 2, "type 'results' is not one of"),
            ("---\nholds_when: >\n  x\n---\n", 2, "this is not YAML"),
            ("---\n  x\n---\n", 2, "there is none"),
            ("---\njust words\n---\n", 2, "expected 'key: value'"),
            (head + "## Evidence\n- outptu: a.log\n", 6, "unknown kind 'outptu'"),
            (head + "## Evidence\n- a.json\n", 6, "cannot tell the kind of a.json"),
            (head + "## Evidence\n- output: a.log extra — c\n", 6, "unexpected 'extra'"),
            (head + "## Evidence\n- reasoning: r.md\n", 6, "the text above '## Evidence'"),
            (head + "## Evidence\nloose text\n", 6, "every line is an item"),
            (head + "## Evidence\n## Evidence\n", 6, "a second '## Evidence'"),
            (head + "## Cites\n## Notes\n", 6, "only '## Evidence' and '## Cites'"),
            (head + "## Cites\n- builds 2026-01-01-x — r\n", 6, "'builds' is not a relation"),
            (head + "## Cites\n- uses something — r\n", 6, "'something' is not a target"),
            (head + "## Cites\n- uses doi:10.1/x at Eq. 3 — r\n", 6, "in double quotes"),
            (head + "## Cites\n- uses doi:10.1/x review — r\n", 6, "path of the source review"),
            (head + '## Cites\n- uses commit at "x" — r\n', 6, "belongs to a paper"),
            (head + '## Cites\n- uses doi:10.1/x at "Eq. 1 — r\n', 6, "never closed"),
            (head + "## Cites\n- uses library:123 — r\n", 6, "36 characters"),
        ]
        for text, line, words in cases:
            with self.subTest(words=words):
                _, errors = claims.parse_claim_md(text)
                self.assertTrue(errors, text)
                self.assertEqual(errors[0][0], line, errors)
                self.assertIn(words, errors[0][1])


class CompileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.org")
        self.git("config", "user.name", "t")
        self.git("remote", "add", "origin", "git@gitlab.example.org:group/transport_sim.git")
        (self.repo / "runs").mkdir()
        (self.repo / "runs" / "sta.log").write_text("residual after hold: 0.009 um\nlinear: 31.1 um\n")
        (self.repo / "runs" / "com.vl.json").write_text(
            '{"mark": "line", "data": {"values": [{"t": 30, "x": 0.009}]}}\n'
        )
        (self.repo / "sim.py").write_text("print(0.009)\n")
        self.git("add", ".")
        self.git("commit", "-qm", "sim")
        self.commit = self.git("rev-parse", "HEAD")
        self.root = self.repo / "claims"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    def new(self, title: str = "STA ramp removes the residual") -> tuple[str, Path]:
        code, out, err = run(self.root, "new", title, "--type", "result")
        self.assertEqual(code, 0, err)
        cid = out.splitlines()[0]
        return cid, self.root / cid

    def write(self, folder: Path, evidence: str, cites: str, reasoning: str = "") -> None:
        (folder / "claim.md").write_text(
            "---\n"
            "title: Simulated STA ramp removes the residual (31.1 → 0.009 um)\n"
            "statement: The STA ramp reduces the residual from 31.1 um to 0.009 um.\n"
            "type: result\n"
            "holds_when: Simulation (transport_sim), noise-free drivers.\n"
            "command: python sim.py --ramp sta\n"
            "contributors: Claude Code (claude-opus-5-5)\n"
            "---\n\n"
            + (reasoning or "The log [1] shows 0.009 um, against 31.1 um before.\n")
            + "\n## Evidence\n" + evidence + "\n## Cites\n" + cites
        )

    def claim(self, cid: str) -> dict:
        return json.loads((self.root / cid / "claim.json").read_text())

    # --- tests -------------------------------------------------------------------

    def test_new_starts_a_claim_md_with_the_commit_and_compiles_it(self) -> None:
        cid, folder = self.new()
        text = (folder / "claim.md").read_text()
        self.assertIn(f"commit: {self.commit}", text)
        self.assertIn("- uses commit", text)
        claim = self.claim(cid)
        self.assertEqual(claim["status"], "draft")
        self.assertEqual(claim["evidence"][0]["file"], "evidence/01-reasoning.md")

    def test_new_json_keeps_the_long_form(self) -> None:
        code, out, _ = run(self.root, "new", "Legacy", "--json")
        self.assertEqual(code, 0)
        folder = self.root / out.splitlines()[0]
        self.assertFalse((folder / "claim.md").exists())
        self.assertTrue((folder / "evidence" / "01-reasoning.md").is_file())

    def test_evidence_is_copied_under_numbered_names_with_its_hash(self) -> None:
        cid, folder = self.new()
        self.write(
            folder,
            "- output: runs/sta.log — Run log, verbatim.\n"
            "- runs/com.vl.json — CoM during the hold.\n"
            "- sim.py\n",
            "- uses commit — The code.\n",
        )
        code, out, _ = run(self.root, "check", cid)
        self.assertEqual(code, 0, out)
        claim = self.claim(cid)
        self.assertEqual(
            [(e["kind"], e["file"]) for e in claim["evidence"]],
            [
                ("reasoning", "evidence/01-reasoning.md"),
                ("output", "evidence/02-output.txt"),
                ("figure", "evidence/03-figure.vl.json"),
                ("code", "evidence/04-code.py"),
            ],
        )
        self.assertEqual(claim["evidence"][2]["format"], "vega-lite")
        self.assertEqual(claim["evidence"][3]["language"], "python")
        self.assertEqual(claim["evidence"][1]["caption"], "Run log, verbatim.")
        source = (self.repo / "runs" / "sta.log").read_bytes()
        self.assertEqual((folder / "evidence" / "02-output.txt").read_bytes(), source)
        record = claim["compiled_from"]["evidence"]["evidence/02-output.txt"]
        self.assertEqual(record, {"from": "runs/sta.log", "sha256": hashlib.sha256(source).hexdigest()})
        self.assertEqual(
            claim["compiled_from"]["claim.md"],
            hashlib.sha256((folder / "claim.md").read_bytes()).hexdigest(),
        )
        self.assertIn("The log [1]", (folder / "evidence" / "01-reasoning.md").read_text())

    def test_a_compiled_claim_passes_check_and_seals(self) -> None:
        cid, folder = self.new()
        self.write(folder, "- output: runs/sta.log — Run log.\n", "- uses commit — The code.\n")
        code, out, _ = run(self.root, "check", cid)
        self.assertEqual(code, 0, out)
        self.assertIn("0 error(s)", out)
        code, out, _ = run(self.root, "seal", cid, "--without-check")
        self.assertEqual(code, 0, out)
        claim = self.claim(cid)
        self.assertEqual(claim["status"], "sealed")
        self.assertEqual(claim["provenance"]["agent"], "Claude Code (claude-opus-5-5)")
        self.assertEqual(claim["provenance"]["command"], "python sim.py --ramp sta")
        code, out, _ = run(self.root, "check", cid)
        self.assertEqual(code, 0, out)

    def test_a_change_after_sealing_is_caught(self) -> None:
        cid, folder = self.new()
        self.write(folder, "- output: runs/sta.log — Run log.\n", "- uses commit — The code.\n")
        self.assertEqual(run(self.root, "seal", cid, "--without-check")[0], 0)
        sealed = (folder / "evidence" / "02-output.txt").read_bytes()

        # The source file is rewritten by a later run: noticed, the copy stands.
        (self.repo / "runs" / "sta.log").write_text("residual after hold: 5 um\n")
        code, out, _ = run(self.root, "check", cid)
        self.assertEqual(code, 0, out)
        self.assertIn("runs/sta.log changed since it was sealed as evidence/02-output.txt", out)
        self.assertEqual((folder / "evidence" / "02-output.txt").read_bytes(), sealed)

        # claim.md edited: an error, and it is not compiled again.
        text = (folder / "claim.md").read_text()
        (folder / "claim.md").write_text(text.replace("0.009 um.", "0.01 um."))
        code, out, _ = run(self.root, "check", cid)
        self.assertEqual(code, 1)
        self.assertIn("claim.md changed after the claim was sealed", out)
        self.assertIn("0.009 um.", self.claim(cid)["statement"])

        # Editing the record of where it came from breaks the seal itself.
        (folder / "claim.md").write_text(text)
        claim = self.claim(cid)
        claim["compiled_from"]["claim.md"] = "0" * 64
        (folder / "claim.json").write_text(json.dumps(claim))
        code, out, _ = run(self.root, "check", cid)
        self.assertIn("changed after it was sealed", out)

    def test_a_draft_follows_its_sources_and_drops_items_removed(self) -> None:
        cid, folder = self.new()
        self.write(
            folder,
            "- output: runs/sta.log — Run log.\n- runs/com.vl.json — CoM.\n",
            "- uses commit — The code.\n",
        )
        run(self.root, "check", cid)
        self.assertTrue((folder / "evidence" / "03-figure.vl.json").is_file())
        (self.repo / "runs" / "sta.log").write_text("residual after hold: 0.009 um\nlinear: 31.1 um\nrerun\n")
        self.write(folder, "- output: runs/sta.log — Run log.\n", "- uses commit — The code.\n")
        run(self.root, "check", cid)
        self.assertFalse((folder / "evidence" / "03-figure.vl.json").exists())
        self.assertIn("rerun", (folder / "evidence" / "02-output.txt").read_text())
        self.assertEqual(len(self.claim(cid)["evidence"]), 2)

    def test_the_commit_citation_comes_from_git(self) -> None:
        cid, folder = self.new()
        self.write(folder, "- output: runs/sta.log — Run log.\n", "- uses commit — The code.\n")
        run(self.root, "check", cid)
        claim = self.claim(cid)
        repo = "https://gitlab.example.org/group/transport_sim"
        self.assertEqual(claim["citations"][0]["external"], f"{repo}/-/commit/{self.commit}")
        self.assertEqual(claim["provenance"]["repository"], repo)
        self.assertEqual(claim["provenance"]["commit"], self.commit)

        # GitHub, with credentials in the remote: dropped, /commit/.
        self.git("remote", "set-url", "origin", "https://u:secret@github.com/org/sim.git")
        run(self.root, "check", cid)
        self.assertEqual(
            self.claim(cid)["citations"][0]["external"],
            f"https://github.com/org/sim/commit/{self.commit}",
        )

    def test_no_web_remote_is_an_error_on_the_line_that_cites_the_commit(self) -> None:
        self.git("remote", "remove", "origin")
        cid, folder = self.new()
        self.assertNotIn("- uses commit", (folder / "claim.md").read_text())
        self.write(folder, "- output: runs/sta.log — Run log.\n", "- uses commit — The code.\n")
        code, out, _ = run(self.root, "check", cid)
        self.assertEqual(code, 1)
        self.assertIn("claim.md:16: the code's repository has no remote 'origin'", out)

    def test_a_large_file_must_be_local_only_with_an_excerpt(self) -> None:
        (self.repo / "runs" / "big.log").write_text("x 0.009\n" * 3000)
        cid, folder = self.new()
        self.write(folder, "- output: runs/big.log — Full log.\n", "- uses commit — The code.\n")
        code, out, _ = run(self.root, "check", cid)
        self.assertEqual(code, 1)
        self.assertIn("claim.md:13: runs/big.log is 24000 characters", out)
        self.assertIn("local-only", out)
        self.write(
            folder,
            "- output: runs/big.log local-only — Full log.\n"
            "- output: runs/sta.log — The lines used.\n",
            "- uses commit — The code.\n",
        )
        code, out, _ = run(self.root, "check", cid)
        self.assertEqual(code, 0, out)
        self.assertTrue(self.claim(cid)["evidence"][1]["local_only"])

    def test_a_cited_claim_and_review_must_exist(self) -> None:
        cid, folder = self.new()
        self.write(
            folder,
            "- output: runs/sta.log — Run log.\n",
            "- extends 2026-01-01-nothing — r\n"
            '- uses doi:10.1/x at "Eq. 1" review sources/doi-10.1-x/r.json — r\n',
        )
        code, out, _ = run(self.root, "check", cid)
        self.assertEqual(code, 1)
        self.assertIn("claim.md:16: no claim 2026-01-01-nothing", out)
        self.assertIn("claim.md:17: no source review sources/doi-10.1-x/r.json", out)

    def test_a_folder_with_only_claim_md_is_compiled_by_check(self) -> None:
        folder = self.root / "2026-11-01-by-hand"
        folder.mkdir(parents=True)
        self.write(folder, "- output: runs/sta.log — Run log.\n", "- uses commit — The code.\n")
        code, out, _ = run(self.root, "check")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.claim("2026-11-01-by-hand")["status"], "draft")

    def test_a_legacy_json_claim_still_seals_and_checks(self) -> None:
        code, out, _ = run(self.root, "new", "Residual", "--type", "result", "--json")
        cid = out.splitlines()[0]
        folder = self.root / cid
        (folder / "evidence" / "01-reasoning.md").write_text("Read off the log.\n")
        (folder / "evidence" / "02-output.txt").write_text("residual 31.1 um\n")
        claim = self.claim(cid)
        claim.update(
            statement="The residual is 31.1 um.",
            holds_when="Simulation.",
            contributors=["Claude Code (claude-opus-5-5)"],
            provenance={"commit": self.commit},
        )
        claim["evidence"].append({"kind": "output", "file": "evidence/02-output.txt"})
        (folder / "claim.json").write_text(json.dumps(claim))
        self.assertEqual(run(self.root, "seal", cid, "--without-check")[0], 0)
        self.assertNotIn("compiled_from", self.claim(cid))
        code, out, _ = run(self.root, "check", cid)
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
