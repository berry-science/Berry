"""Tests for the independent check of a draft in claims.py: `checked`, and
what `pending` and `seal` make of it.

    python3 -m unittest discover -s tests
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

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "claims" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import claims  # noqa: E402

AGENT = "claim-checker (claude-opus-5-5)"
ISSUE = {
    "severity": "major",
    "text": "The statement says 0.009 um; the log shows 0.09 um. Write 0.09 um.",
    "quote": "0.009 um",
    "file": "claim.md",
}


def run(root: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = claims.main(["--root", str(root), *args])
    return code, out.getvalue(), err.getvalue()


class CheckedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.org")
        self.git("config", "user.name", "t")
        self.git("remote", "add", "origin", "git@gitlab.example.org:group/transport_sim.git")
        (self.repo / "runs").mkdir()
        (self.repo / "runs" / "sta.log").write_text("residual after hold: 0.009 um\nlinear: 31.1 um\n")
        (self.repo / "sim.py").write_text("print(0.009)\n")
        self.git("add", ".")
        self.git("commit", "-qm", "sim")
        self.root = self.repo / "claims"
        code, out, err = run(self.root, "new", "STA ramp removes the residual", "--type", "result")
        self.assertEqual(code, 0, err)
        self.cid = out.splitlines()[0]
        self.folder = self.root / self.cid
        self.write()
        self.issues = self.repo / "issues.json"
        self.issues.write_text(json.dumps([ISSUE]))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    def write(self, holds_when: str = "Simulation, noise-free drivers.") -> None:
        (self.folder / "claim.md").write_text(
            "---\n"
            "title: Simulated STA ramp removes the residual (31.1 → 0.009 um)\n"
            "statement: The STA ramp reduces the residual from 31.1 um to 0.009 um.\n"
            "type: result\n"
            f"holds_when: {holds_when}\n"
            "command: python sim.py --ramp sta\n"
            "contributors: Claude Code (claude-opus-5-5)\n"
            "---\n\n"
            "The log [1] shows 0.009 um, against 31.1 um before.\n"
            "\n## Evidence\n- output: runs/sta.log — Run log.\n"
            "\n## Cites\n- uses commit — The code.\n"
        )

    def checked(self, *args: str) -> tuple[int, str, str]:
        return run(self.root, "checked", self.cid, *args, "--agent", AGENT)

    def rounds(self) -> list[dict]:
        return json.loads((self.folder / "checks.json").read_text())["rounds"]

    def claim(self) -> dict:
        return json.loads((self.folder / "claim.json").read_text())

    # --- recording a round ----------------------------------------------------

    def test_a_pass_is_recorded_with_the_hash_the_seal_will_have(self) -> None:
        code, out, err = self.checked("--pass")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), f"{self.cid}: passed in round 1; seal it: claims.py seal {self.cid}")
        [r] = self.rounds()
        self.assertEqual((r["round"], r["verdict"], r["issues"], r["agent"]), (1, "pass", [], AGENT))
        self.assertIn("at", r)
        code, out, _ = run(self.root, "seal", self.cid)
        self.assertEqual(code, 0, out)
        seal = self.claim()["seal"]
        self.assertEqual(seal["sha256"], r["content"])
        self.assertEqual(seal["checked"], 1)
        # checks.json is outside the seal: the sealed claim checks clean.
        code, out, _ = run(self.root, "check", self.cid)
        self.assertEqual(code, 0, out)

    def test_issues_use_the_audit_format_and_go_back_to_the_author(self) -> None:
        code, out, err = self.checked("--issues", str(self.issues))
        self.assertEqual(code, 0, err)
        self.assertIn("1 issue(s) in round 1, worst major; the author fixes or answers them, "
                      "then round 2", out)
        self.assertEqual(self.rounds()[0]["issues"], [ISSUE])
        self.assertEqual(self.rounds()[0]["verdict"], "issues")
        _, out, _ = run(self.root, "pending")
        self.assertIn("issues in round 1 (1 issue(s), worst major): waiting for the author's fix", out)
        code, out, _ = run(self.root, "seal", self.cid)
        self.assertEqual(code, 1)
        self.assertIn("not sealed", out)
        # The author fixes it; round 2 passes; it seals.
        self.write(holds_when="Simulation, noise-free drivers, one ramp shape.")
        _, out, _ = run(self.root, "pending")
        self.assertIn("changed since: ready for round 2", out)
        self.assertEqual(self.checked("--pass")[0], 0)
        self.assertEqual([r["round"] for r in self.rounds()], [1, 2])
        self.assertEqual(run(self.root, "seal", self.cid)[0], 0)
        self.assertEqual(self.claim()["seal"]["checked"], 2)

    def test_issues_in_round_two_hold_the_draft_and_there_is_no_third_round(self) -> None:
        self.checked("--issues", str(self.issues))
        self.write(holds_when="Simulation.")
        code, out, _ = self.checked("--issues", str(self.issues))
        self.assertEqual(code, 0)
        self.assertIn("held for the researcher (claims.py pending)", out)
        _, out, _ = run(self.root, "pending")
        self.assertIn("held: round 2 found 1 issue(s), worst major; the researcher decides", out)
        self.assertIn('- major: The statement says 0.009 um; the log shows 0.09 um. Write 0.09 um. '
                      '— "0.009 um" (claim.md)', out)
        self.write(holds_when="Simulation, once more.")
        code, _, err = self.checked("--pass")
        self.assertEqual(code, 2)
        self.assertIn("no third round", err)
        self.assertEqual(len(self.rounds()), 2)
        code, out, _ = run(self.root, "seal", self.cid)
        self.assertEqual(code, 1)
        self.assertIn("is held", out)
        # The researcher may seal it anyway, by hand.
        self.assertEqual(run(self.root, "seal", self.cid, "--without-check")[0], 0)
        self.assertIs(self.claim()["seal"]["checked"], False)

    def test_a_change_after_a_pass_needs_checking_again(self) -> None:
        self.checked("--pass")
        self.write(holds_when="Simulation, a broader range than was run.")
        code, out, _ = run(self.root, "seal", self.cid)
        self.assertEqual(code, 1)
        self.assertIn("changed after its pass in round 1: check it again (round 2)", out)
        _, out, _ = run(self.root, "pending")
        self.assertIn("changed after its pass in round 1", out)
        self.assertEqual(self.checked("--pass")[0], 0)
        self.assertEqual(run(self.root, "seal", self.cid)[0], 0)

    def test_an_evidence_change_after_a_pass_is_seen_too(self) -> None:
        self.checked("--pass")
        (self.repo / "runs" / "sta.log").write_text("residual after hold: 0.5 um\nlinear: 31.1 um\n")
        code, out, _ = run(self.root, "seal", self.cid)
        self.assertEqual(code, 1, out)

    def test_unchanged_content_that_passed_is_not_checked_again(self) -> None:
        self.checked("--pass")
        code, _, err = self.checked("--pass")
        self.assertEqual(code, 2)
        self.assertIn("passed round 1 as it is now: seal it", err)
        self.assertEqual(len(self.rounds()), 1)

    # --- refusals -----------------------------------------------------------------

    def test_an_unchecked_draft_is_not_sealed_unless_the_researcher_says_so(self) -> None:
        code, out, _ = run(self.root, "seal", self.cid)
        self.assertEqual(code, 1)
        self.assertIn("has not been checked", out)
        self.assertEqual(self.claim()["status"], "draft")
        _, out, _ = run(self.root, "pending")
        self.assertIn("written: not checked yet", out)
        self.assertEqual(run(self.root, "seal", self.cid, "--without-check")[0], 0)
        self.assertFalse((self.folder / "checks.json").exists())

    def test_a_draft_with_check_errors_cannot_pass(self) -> None:
        self.write(holds_when="x" * 2001)  # compiles, but check says it is too long
        code, out, err = self.checked("--pass")
        self.assertEqual(code, 2)
        self.assertIn("cannot pass: record them as issues", err)
        self.assertIn("ERROR", out)
        self.assertFalse((self.folder / "checks.json").exists())

    def test_the_issues_file_is_validated(self) -> None:
        for bad in ([{"severity": "huge", "text": "x"}], [{"severity": "minor"}], {"text": "x"}):
            self.issues.write_text(json.dumps(bad))
            self.assertEqual(self.checked("--issues", str(self.issues))[0], 2)
        self.issues.write_text("[]")
        code, _, err = self.checked("--issues", str(self.issues))
        self.assertEqual(code, 2)
        self.assertIn("--pass", err)
        self.assertFalse((self.folder / "checks.json").exists())

    def test_a_sealed_claim_is_audited_not_checked(self) -> None:
        run(self.root, "seal", self.cid, "--without-check")
        code, _, err = self.checked("--pass")
        self.assertEqual(code, 2)
        self.assertIn("audited", err)

    def test_checks_json_is_committed_with_the_claim(self) -> None:
        self.checked("--pass")
        (self.repo / ".gitignore").write_text("checks.json\n")
        code, out, _ = run(self.root, "seal", self.cid)
        self.assertEqual(code, 1)
        self.assertIn("checks.json is ignored by git", out)


if __name__ == "__main__":
    unittest.main()
