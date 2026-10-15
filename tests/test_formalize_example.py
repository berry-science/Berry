"""The worked example of formalize-derivation: a textbook Gaussian-beam
derivation recorded as a draft claim in a fixture ledger.

    tests/fixtures/formalize-derivation/claims/2026-10-13-gaussian-beam-paraxial-mode-checks/

The ledger check is standard library and always runs. Re-running the check
script needs SymPy; it runs on a copy, so the fixture is never rewritten.
To regenerate the fixture after changing the helper, see
tests/fixtures/formalize-derivation/README.md.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "formalize-derivation" / "scripts"
LEDGER = ROOT / "tests" / "fixtures" / "formalize-derivation" / "claims"
CID = "2026-10-13-gaussian-beam-paraxial-mode-checks"
sys.path.insert(0, str(ROOT / "skills" / "record-claim" / "scripts"))
sys.path.insert(0, str(SCRIPTS))

import claims  # noqa: E402
import derivfmt  # noqa: E402

try:
    import mpmath  # noqa: F401
    import sympy  # noqa: F401

    HAVE_SYMPY = True
except ImportError:  # pragma: no cover
    HAVE_SYMPY = False


class ExampleLedgerTest(unittest.TestCase):
    def test_the_example_checks_without_errors(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = claims.main(["--root", str(LEDGER), "check"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("0 error(s)", out.getvalue())

    def test_it_is_a_draft_and_its_exports_are_version_0(self) -> None:
        claim = json.loads((LEDGER / CID / "claim.json").read_text())
        self.assertEqual(claim["status"], "draft")
        self.assertNotIn("seal", claim)
        kinds = [item["kind"] for item in claim["evidence"]]
        self.assertEqual(kinds[:3], ["reasoning", "derivation", "code"])
        for item in claim["evidence"]:
            if item["kind"] == "data":
                data = json.loads((LEDGER / CID / item["file"]).read_text())
                self.assertEqual(data["format_version"], 0)
                self.assertEqual(data["backend"], "sympy")

    def test_every_label_is_checked_and_the_verdicts_are_as_recorded(self) -> None:
        text = (LEDGER / CID / "evidence" / "04-output.txt").read_text()
        run = derivfmt.RunOutput(text)
        self.assertEqual(run.problems, [])
        tex = (LEDGER / CID / "evidence" / "02-derivation.tex").read_text()
        self.assertEqual(sorted(derivfmt.tex_labels(tex)), sorted(run.summary()["labels"]))
        self.assertEqual(run.summary()["labels"], {
            "step:mode": "unchecked",
            "step:paraxial": "proved-symbolic",
            "step:inverse-q": "proved-symbolic",
            "step:exponent": "proved-symbolic",
            "step:phase-dims": "dims-only",
            "step:gouy": "proved-symbolic",
            "step:waist": "limit-only",
            "step:divergence": "limit-only",
            "step:near-waist": "series-verified",
        })
        self.assertEqual(run.header["runner"], "uv")

    def test_the_excerpt_is_the_human_part_of_the_output(self) -> None:
        full = (LEDGER / CID / "evidence" / "04-output.txt").read_text().splitlines()
        excerpt = (LEDGER / CID / "evidence" / "05-output.txt").read_text().splitlines()
        self.assertEqual(excerpt, [line for line in full if not line.startswith("{")])


@unittest.skipUnless(HAVE_SYMPY, "SymPy/mpmath not installed: python3 -m pip install sympy mpmath pint")
class ExampleRerunTest(unittest.TestCase):
    def test_a_rerun_gives_the_same_verdicts_and_exports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp) / "evidence"
            shutil.copytree(LEDGER / CID / "evidence", ev)
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "formalize.py"), "run", str(ev / "03-code.py"),
                 "--out", str(ev / "rerun.txt"), "--no-uv"],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            old = derivfmt.comparable((ev / "04-output.txt").read_text())
            new = derivfmt.comparable((ev / "rerun.txt").read_text())
        # The header names the environment (versions, runner), which may differ
        # here from the recorded uv run; what was checked may not.
        self.assertEqual(old[1:], new[1:])


if __name__ == "__main__":
    unittest.main()
