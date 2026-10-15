"""Tests for formalize-derivation's coverage check and its hook in claims.py.

    python3 -m unittest discover -s tests

Each test builds a throwaway ledger with one claim holding a labeled
derivation, a check script, the script's verbatim output and an exported
result, runs `claims.py check` on it as an agent would, and then breaks
one thing. The tests that run a check script need SymPy and are skipped
without it; the rest are standard library.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "formalize-derivation" / "scripts"
sys.path.insert(0, str(ROOT / "skills" / "record-claim" / "scripts"))
sys.path.insert(0, str(SCRIPTS))

import claims  # noqa: E402
import derivcover  # noqa: E402
import derivfmt  # noqa: E402

try:
    import mpmath  # noqa: F401
    import sympy  # noqa: F401

    HAVE_SYMPY = True
except ImportError:  # pragma: no cover
    HAVE_SYMPY = False

needs_sympy = unittest.skipUnless(
    HAVE_SYMPY, "SymPy/mpmath not installed: python3 -m pip install sympy mpmath pint"
)

CID = "2026-10-13-gaussian-beam-q-parameter"

TEX = r"""
\begin{align}
  w(z)^2 &= w_0^2\left(1 + \frac{z^2}{z_R^2}\right),\quad z_R = \frac{\pi w_0^2}{\lambda} \label{step:w}\\
  \frac{1}{q(z)} &= \frac{1}{z + i z_R} = \frac{1}{R(z)} - \frac{i\lambda}{\pi w(z)^2} \label{step:q}
\end{align}
At the waist the beam radius is $w_0$:
\begin{equation}
  \lim_{z\to 0} w(z) = w_0 \label{step:waist}
\end{equation}
"""

SCRIPT = '''
# /// script
# requires-python = ">=3.10"
# dependencies = ["sympy==1.14.0", "mpmath==1.3.0", "pint==0.24.4"]
# ///
import derivcheck as dc

dc.begin(tex="02-derivation.tex", seed=20261013)
z = dc.symbol("z", "z", dim="length", positive=True)
w0 = dc.symbol("w0", "w_0", dim="length", positive=True, convention="beam-radius-1e2@1")
lam = dc.symbol("lam", r"\\lambda", dim="length", positive=True)
zR = dc.pi * w0**2 / lam
w2 = w0**2 * (1 + (z / zR) ** 2)
R = z * (1 + (zR / z) ** 2)

dc.unchecked("step:w", "definition", "the standard beam radius and Rayleigh range")
dc.step("step:q", 1 / (z + dc.I * zR), 1 / R - dc.I * lam / (dc.pi * w2))
dc.limit_case("step:waist", dc.sqrt(w2), z, 0, w0)
dc.export("inverse_q", "step:q")
dc.finish()
'''

CONVENTIONS = {
    "conventions": [
        {"key": "beam-radius-1e2", "category": "definition", "versions": [
            {"version": 1, "statement": "w is the 1/e² intensity radius.", "since": "2026-10-13"}
        ]}
    ]
}


def check(root: Path, *ids: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = claims.main(["--root", str(root), "check", *ids])
    return code, out.getvalue()


class Ledger:
    """A git repository with a ledger holding one derivation claim."""

    def __init__(self, tex: str = TEX, script: str | None = SCRIPT, statement: str | None = None):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git = ["git", "-C", str(self.repo)]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "config", "user.email", "t@example.org"], check=True)
        subprocess.run([*git, "config", "user.name", "t"], check=True)
        (self.repo / "README").write_text("fixture\n")
        subprocess.run([*git, "add", "."], check=True)
        subprocess.run([*git, "commit", "-qm", "init"], check=True)
        self.commit = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        self.root = self.repo / "claims"
        self.folder = self.root / CID
        self.ev = self.folder / "evidence"
        self.ev.mkdir(parents=True)
        (self.root / "conventions.json").write_text(json.dumps(CONVENTIONS, indent=2))
        (self.ev / "01-reasoning.md").write_text("The q parameter of a Gaussian beam, checked step by step.\n")
        (self.ev / "02-derivation.tex").write_text(textwrap.dedent(tex))
        evidence = [
            {"kind": "reasoning", "file": "evidence/01-reasoning.md", "format": "markdown"},
            {"kind": "derivation", "file": "evidence/02-derivation.tex", "format": "latex"},
        ]
        if script is not None:
            (self.ev / "03-code.py").write_text(script.lstrip())
            evidence.append({"kind": "code", "file": "evidence/03-code.py", "language": "python"})
        self.claim = {
            "id": CID,
            "status": "draft",
            "title": "Model: 1/q = 1/R - i lambda/(pi w^2) for q = z + i z_R",
            "statement": statement or "In the paraxial model, q = z + i z_R satisfies 1/q = 1/R(z) - i lambda/(pi w(z)^2).",
            "claim_type": "result",
            "holds_when": "Model: paraxial scalar Gaussian beam in free space; z > 0.",
            "evidence": evidence,
            "citations": [],
            "conventions": ["beam-radius-1e2@1"],
            "contributors": [],
            "anchors": [],
            "provenance": {"commit": self.commit},
            "library": None,
        }
        self.save()

    def save(self) -> None:
        (self.folder / "claim.json").write_text(json.dumps(self.claim, indent=2))

    def run_script(self) -> None:
        """Run the check as the skill says, and list the output and export."""
        out = self.ev / "04-output.txt"
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "formalize.py"), "run", str(self.ev / "03-code.py"),
             "--out", str(out), "--no-uv"],
            capture_output=True, text=True,
        )
        self.run_code = proc.returncode
        self.claim["evidence"].append({"kind": "output", "file": "evidence/04-output.txt", "caption": "Check output, verbatim."})
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "formalize.py"), "export", str(out), "inverse_q",
             str(self.ev / "05-data.json")],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            self.claim["evidence"].append({"kind": "data", "file": "evidence/05-data.json", "format": "json",
                                           "caption": "Exported result inverse_q (format_version 0)."})
        self.save()

    def cover(self) -> tuple[list[str], list[str]]:
        return derivcover.check_claim(self.folder, json.loads((self.folder / "claim.json").read_text()))

    def close(self) -> None:
        self.tmp.cleanup()


@needs_sympy
class ClaimIdTest(unittest.TestCase):
    """formalize.py by claim id, from the repository root: one command, no cd."""

    def formalize(self, cwd: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPTS / "formalize.py"), *args],
                              cwd=cwd, capture_output=True, text=True)

    def test_run_export_and_cover_by_claim_id(self) -> None:
        led = Ledger()
        try:
            proc = self.formalize(led.repo, "run", CID, "--no-uv")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((led.ev / "04-output.txt").is_file())
            self.assertIn('"file": "evidence/04-output.txt"', proc.stderr)
            proc = self.formalize(led.repo, "export", CID, "inverse_q")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((led.ev / "05-data.json").is_file())
            self.assertIn('"file": "evidence/05-data.json"', proc.stdout)
            led.claim["evidence"] += [
                {"kind": "output", "file": "evidence/04-output.txt", "caption": "Output, verbatim."},
                {"kind": "data", "file": "evidence/05-data.json", "format": "json", "caption": "Export."},
            ]
            led.save()
            proc = self.formalize(led.repo, "cover", CID)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("0 error(s)", proc.stdout)

            # Listed now: a second run and export go to the same files.
            proc = self.formalize(led.repo, "run", CID, "--no-uv")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn("List it", proc.stderr)
            proc = self.formalize(led.repo, "export", CID, "inverse_q")
            self.assertIn("05-data.json", proc.stdout)
            self.assertFalse((led.ev / "06-data.json").exists())

            # From elsewhere, with --root.
            with tempfile.TemporaryDirectory() as elsewhere:
                proc = self.formalize(Path(elsewhere), "--root", str(led.root), "cover", CID)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        finally:
            led.close()

    def test_as_written_by_claim_id_and_unknown_ids(self) -> None:
        led = Ledger(script=SCRIPT.replace("1 / (z + dc.I * zR)", "1 / (z - dc.I * zR)"))
        try:
            proc = self.formalize(led.repo, "run", CID, "--as-written", "--no-uv")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((led.ev / "04-output.as-written.txt").is_file())
            self.assertTrue((led.ev / "03-code.as-written.py").is_file())
            self.assertFalse((led.ev / "04-output.txt").exists())
            against = led.repo / "subs.json"
            against.write_text(json.dumps({"step:q": "1/(z + I*pi*w0**2/lam)"}))
            proc = self.formalize(led.repo, "run", CID, "--against", str(against), "--no-uv")
            self.assertFalse((led.ev / "04-output.txt").exists(), "a red run wrote over the evidence")
            proc = self.formalize(led.repo, "run", "2026-01-01-no-such-claim", "--no-uv")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("no claim 2026-01-01-no-such-claim", proc.stderr)
        finally:
            led.close()


class WithoutSympyTest(unittest.TestCase):
    """Standard library only: what claims.py says before any check has run."""

    def test_a_derivation_without_a_check_is_a_warning_not_an_error(self) -> None:
        led = Ledger(script=None)
        try:
            code, out = check(led.root, CID)
            self.assertEqual(code, 0, out)
            self.assertIn("the derivation has no check", out)
            self.assertIn("strongly encouraged", out)
        finally:
            led.close()

    def test_a_script_that_prints_its_own_pass_is_an_error(self) -> None:
        led = Ledger(script=SCRIPT.replace("dc.finish()", 'print("all steps PASS")\ndc.finish()'))
        try:
            code, out = check(led.root, CID)
            self.assertEqual(code, 1, out)
            self.assertIn("[prints-verdict]", out)
            self.assertIn("never run into an output item", out)
        finally:
            led.close()

    def test_claims_without_a_derivation_are_untouched(self) -> None:
        led = Ledger(script=None)
        try:
            led.claim["evidence"] = led.claim["evidence"][:1]
            led.save()
            _, out = check(led.root, CID)
            self.assertNotIn("derivation", out)
        finally:
            led.close()

    def test_the_hook_does_nothing_without_the_skill(self) -> None:
        # record-claim installed on its own: the same claims.py, no
        # formalize-derivation beside it.
        led = Ledger(script=SCRIPT.replace("dc.finish()", 'print("PASS")\ndc.finish()'))
        with tempfile.TemporaryDirectory() as tmp:
            alone = Path(tmp) / "skills" / "record-claim" / "scripts"
            alone.mkdir(parents=True)
            shutil.copy(ROOT / "skills" / "record-claim" / "scripts" / "claims.py", alone / "claims.py")
            proc = subprocess.run(
                [sys.executable, str(alone / "claims.py"), "--root", str(led.root), "check", CID],
                capture_output=True, text=True,
            )
        led.close()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("prints-verdict", proc.stdout)
        self.assertNotIn("no check", proc.stdout)

    def test_a_broken_coverage_module_is_a_warning(self) -> None:
        led = Ledger(script=None)
        try:
            original = derivcover.check_claim
            with tempfile.TemporaryDirectory() as tmp:
                skills = Path(tmp) / "skills"
                shutil.copytree(ROOT / "skills" / "record-claim", skills / "record-claim")
                broken = skills / "formalize-derivation" / "scripts"
                broken.mkdir(parents=True)
                (broken / "derivcover.py").write_text("def check_claim(folder, claim):\n    raise RuntimeError('boom')\n")
                proc = subprocess.run(
                    [sys.executable, str(skills / "record-claim" / "scripts" / "claims.py"),
                     "--root", str(led.root), "check", CID],
                    capture_output=True, text=True,
                )
            self.assertIs(derivcover.check_claim, original)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("could not run: boom", proc.stdout)
        finally:
            led.close()


@needs_sympy
class CoverageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.led = Ledger()
        cls.led.run_script()
        cls.output = (cls.led.ev / "04-output.txt").read_text()
        cls.export = (cls.led.ev / "05-data.json").read_text()
        cls.claim = json.loads((cls.led.folder / "claim.json").read_text())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.led.close()

    def setUp(self) -> None:
        # Each test starts from the clean, checked claim.
        (self.led.ev / "04-output.txt").write_text(self.output)
        (self.led.ev / "05-data.json").write_text(self.export)
        (self.led.ev / "02-derivation.tex").write_text(textwrap.dedent(TEX))
        (self.led.ev / "03-code.py").write_text(SCRIPT.lstrip())
        self.led.claim = json.loads(json.dumps(self.claim))
        self.led.save()

    def test_the_clean_claim_has_no_errors(self) -> None:
        self.assertEqual(self.led.run_code, 0)
        code, out = check(self.led.root, CID)
        self.assertEqual(code, 0, out)
        errors, warnings = self.led.cover()
        self.assertEqual(errors, [])
        # step:w is a definition: not a warning. The limit check is a weak one.
        self.assertFalse(any("step:w:" in w for w in warnings), warnings)

    def test_an_uncovered_label_is_a_warning(self) -> None:
        # The derivation gains a step after the run: re-run, and the new label is
        # not checked by the script.
        tex = TEX.replace(r"\end{align}", "  R(z) &= z + z_R^2/z \\label{step:R}\n\\end{align}")
        (self.led.ev / "02-derivation.tex").write_text(textwrap.dedent(tex))
        led2 = Ledger(tex=tex)
        try:
            led2.run_script()
            errors, warnings = led2.cover()
            self.assertEqual(errors, [])
            self.assertIn("step:R: in the derivation, but no check of it ran", warnings)
        finally:
            led2.close()

    def test_an_output_label_missing_from_the_tex_is_an_error(self) -> None:
        tex = TEX.replace(r"\label{step:waist}", r"\label{step:waist-radius}")
        led2 = Ledger(tex=tex)
        try:
            led2.run_script()
            errors, _ = led2.cover()
            self.assertIn(
                "step:waist: checked in the output, but there is no such \\label in the derivation", errors
            )
        finally:
            led2.close()

    def test_a_failing_step_is_an_error(self) -> None:
        led2 = Ledger(script=SCRIPT.replace("1 / (z + dc.I * zR)", "1 / (z - dc.I * zR)"))
        try:
            led2.run_script()
            self.assertEqual(led2.run_code, 1)
            code, out = check(led2.root, CID)
            self.assertEqual(code, 1)
            self.assertIn("step:q: FAIL (step)", out)
        finally:
            led2.close()

    def test_an_edited_output_is_an_error(self) -> None:
        text = self.output.replace('"verdict":"limit-only"', '"verdict":"proved-symbolic"')
        self.assertNotEqual(text, self.output)
        (self.led.ev / "04-output.txt").write_text(text)
        errors, _ = self.led.cover()
        self.assertTrue(any("not written by the helper" in e for e in errors), errors)

    def test_a_hand_added_verdict_is_an_error(self) -> None:
        (self.led.ev / "04-output.txt").write_text(self.output + "step:R  PASS\n")
        errors, _ = self.led.cover()
        self.assertTrue(any("a verdict the helper did not write" in e for e in errors), errors)

    def test_a_changed_script_or_tex_is_an_error(self) -> None:
        (self.led.ev / "03-code.py").write_text(SCRIPT.lstrip() + "\n# edited\n")
        errors, _ = self.led.cover()
        self.assertTrue(any("another version of 03-code.py" in e for e in errors), errors)
        (self.led.ev / "03-code.py").write_text(SCRIPT.lstrip())
        (self.led.ev / "02-derivation.tex").write_text(textwrap.dedent(TEX) + "% edited\n")
        errors, _ = self.led.cover()
        self.assertTrue(any("the derivation changed after the run" in e for e in errors), errors)

    def test_the_export_holds_the_result_and_its_weakest_verdict(self) -> None:
        data = json.loads(self.export)
        self.assertEqual(data["format_version"], 0)
        self.assertEqual(data["result"], "inverse_q")
        self.assertEqual(data["backend"], "sympy")
        self.assertEqual(data["verdict"], "proved-symbolic")
        self.assertEqual(data["path"], {"step:q": "proved-symbolic"})
        self.assertEqual(data["step"], "step:q")
        self.assertIsNone(data["regime"])
        self.assertEqual(set(data["symbols"]), {"z", "w0", "lam"})
        self.assertEqual(data["symbols"]["w0"]["convention"], "beam-radius-1e2@1")
        self.assertEqual(sympy.srepr(sympy.sympify(data["expr"])), data["expr"])

    def test_an_edited_export_is_an_error(self) -> None:
        data = json.loads(self.export)
        data["verdict"] = "formal"
        (self.led.ev / "05-data.json").write_text(json.dumps(data))
        errors, _ = self.led.cover()
        self.assertTrue(any("differs from what the helper exported, in verdict" in e for e in errors), errors)

    def test_a_sealed_claim_with_a_v0_export_is_an_error(self) -> None:
        self.led.claim["status"] = "sealed"
        self.led.save()
        errors, _ = derivcover.check_claim(self.led.folder, self.led.claim)
        self.assertTrue(any("format_version 0 may still change" in e for e in errors), errors)

    def test_a_statement_stronger_than_its_checks_is_an_error(self) -> None:
        led2 = Ledger(script=SCRIPT.replace('dc.export("inverse_q", "step:q")', ""),
                      statement="Verified: at the waist the beam radius of the model is w0.")
        try:
            led2.run_script()
            errors, _ = led2.cover()
            self.assertTrue(any("says 'Verified'" in e and "step:waist (limit-only)" in e for e in errors), errors)
        finally:
            led2.close()

    def test_a_convention_missing_from_the_ledger_is_an_error(self) -> None:
        (self.led.root / "conventions.json").write_text(json.dumps({"conventions": []}))
        try:
            errors, _ = self.led.cover()
            self.assertTrue(any("convention beam-radius-1e2@1 is not in conventions.json" in e for e in errors), errors)
        finally:
            (self.led.root / "conventions.json").write_text(json.dumps(CONVENTIONS, indent=2))

    def test_a_red_run_is_not_evidence(self) -> None:
        against = self.led.repo / "against.json"
        against.write_text(json.dumps({"step:q": "1/(z - I*pi*w0**2/lam)"}))
        out = self.led.repo / "red.txt"
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "formalize.py"), "run", str(self.led.ev / "03-code.py"),
             "--out", str(out), "--no-uv", "--against", str(against)],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn('"against":true', out.read_text())
        (self.led.ev / "04-output.txt").write_text(out.read_text())
        errors, _ = self.led.cover()
        self.assertTrue(any("is a red run, not evidence" in e for e in errors), errors)

    def test_a_failing_as_written_run_is_kept_as_evidence(self) -> None:
        # The derivation as found has a sign error in step:q. Its check is run
        # first, as written; then .tex and script are fixed and run again.
        wrong = SCRIPT.replace("1 / (z + dc.I * zR)", "1 / (z - dc.I * zR)")
        led2 = Ledger(script=wrong)
        try:
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "formalize.py"), "run", str(led2.ev / "03-code.py"),
                 "--as-written", "--no-uv"],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("step:q failed", proc.stderr)
            self.assertIn('"caption": "As written:', proc.stderr)
            for name in ("02-derivation.as-written.tex", "03-code.as-written.py", "04-output.as-written.txt"):
                self.assertTrue((led2.ev / name).is_file(), name)
            written = (led2.ev / "04-output.as-written.txt").read_text()
            self.assertIn('"verdict":"FAIL"', written)

            # Fix the .tex, then the script, and run again.
            (led2.ev / "02-derivation.tex").write_text(textwrap.dedent(TEX) + "% step:q: sign of i z_R corrected\n")
            (led2.ev / "03-code.py").write_text(SCRIPT.lstrip())
            led2.run_script()
            self.assertEqual(led2.run_code, 0)
            led2.claim["evidence"] += [
                {"kind": "derivation", "file": "evidence/02-derivation.as-written.tex", "format": "latex",
                 "caption": "As written: the derivation as it was found."},
                {"kind": "code", "file": "evidence/03-code.as-written.py", "language": "python",
                 "caption": "As written: its check."},
                {"kind": "output", "file": "evidence/04-output.as-written.txt",
                 "caption": "As written: its output, verbatim."},
            ]
            led2.save()
            code, out = check(led2.root, CID)
            self.assertEqual(code, 0, out)
            self.assertIn("step:q failed on the derivation as it was found", out)
            errors, _ = led2.cover()
            self.assertEqual(errors, [])

            # Without the corrected run, the as-written run alone does not pass.
            led2.claim["evidence"] = [i for i in led2.claim["evidence"]
                                      if i.get("file") not in ("evidence/04-output.txt", "evidence/05-data.json")]
            led2.save()
            code, out = check(led2.root, CID)
            self.assertEqual(code, 1, out)
            self.assertIn("no run of the derivation the result rests on", out)

            # Without the marker, the same failing output is an error, as before.
            for item in led2.claim["evidence"]:
                if item.get("file") == "evidence/04-output.as-written.txt":
                    item["caption"] = "Output, verbatim."
            led2.save()
            code, out = check(led2.root, CID)
            self.assertEqual(code, 1, out)
            self.assertIn("step:q: FAIL (step)", out)
        finally:
            led2.close()

    def test_an_as_written_output_must_match_its_copies(self) -> None:
        wrong = SCRIPT.replace("1 / (z + dc.I * zR)", "1 / (z - dc.I * zR)")
        led2 = Ledger(script=wrong)
        try:
            subprocess.run(
                [sys.executable, str(SCRIPTS / "formalize.py"), "run", str(led2.ev / "03-code.py"),
                 "--as-written", "--no-uv"],
                capture_output=True, text=True,
            )
            (led2.ev / "03-code.py").write_text(SCRIPT.lstrip())
            led2.run_script()
            (led2.ev / "02-derivation.as-written.tex").write_text("% edited afterward\n" + textwrap.dedent(TEX))
            led2.claim["evidence"] += [
                {"kind": "derivation", "file": "evidence/02-derivation.as-written.tex", "caption": "As written: tex"},
                {"kind": "code", "file": "evidence/03-code.as-written.py", "language": "python",
                 "caption": "As written: script"},
                {"kind": "output", "file": "evidence/04-output.as-written.txt", "caption": "as written: output"},
            ]
            led2.save()
            errors, _ = led2.cover()
            # The .tex as it was run is the current one, unchanged: it still pairs by
            # hash. The edited copy is not what was run, so it does not stand in for it.
            self.assertEqual(errors, [])
            (led2.ev / "02-derivation.tex").write_text(textwrap.dedent(TEX) + "% corrected\n")
            led2.run_script()
            errors, _ = led2.cover()
            self.assertTrue(any("(output, as written)" in e and "derivation changed after the run" in e
                                for e in errors), errors)
        finally:
            led2.close()

    def test_an_unexported_result_is_a_warning(self) -> None:
        led2 = Ledger(script=SCRIPT.replace('dc.export("inverse_q", "step:q")', ""))
        try:
            led2.run_script()
            errors, warnings = led2.cover()
            self.assertEqual(errors, [])
            self.assertTrue(any('the result is not exported: dc.export("<name>", "step:q")' in w
                                for w in warnings), warnings)
        finally:
            led2.close()
        errors, warnings = self.led.cover()
        self.assertFalse(any("not exported" in w for w in warnings), warnings)

    def test_the_marker_is_a_caption_prefix(self) -> None:
        self.assertTrue(derivfmt.is_as_written({"caption": "As written: the notes"}))
        self.assertTrue(derivfmt.is_as_written({"caption": "  as written: x"}))
        self.assertFalse(derivfmt.is_as_written({"caption": "Output, as written by the helper"}))
        self.assertFalse(derivfmt.is_as_written({}))

    def test_a_rerun_compares_equal(self) -> None:
        out = self.led.repo / "rerun.txt"
        subprocess.run(
            [sys.executable, str(SCRIPTS / "formalize.py"), "run", str(self.led.ev / "03-code.py"),
             "--out", str(out), "--no-uv"],
            capture_output=True, text=True,
        )
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "formalize.py"), "compare", str(self.led.ev / "04-output.txt"), str(out)],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)


if __name__ == "__main__":
    unittest.main()
