"""Tests for skills/formalize-derivation: the helper, its verdict lines and
the linter.

    python3 -m unittest discover -s tests

The helper needs SymPy and mpmath (pint is optional). Without them the
helper tests are skipped, loudly; the linter and the format tests are
standard library and always run.

Every case is a textbook result, and each is shown twice: right, it passes;
wrong, it fails (or warns). No unpublished material.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "formalize-derivation" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import derivfmt  # noqa: E402
import derivlint  # noqa: E402

try:
    import mpmath  # noqa: F401
    import sympy  # noqa: F401

    import derivcheck as dc

    HAVE_SYMPY = True
except ImportError:  # pragma: no cover - depends on the machine
    HAVE_SYMPY = False

needs_sympy = unittest.skipUnless(
    HAVE_SYMPY, "SymPy/mpmath not installed: python3 -m pip install sympy mpmath pint"
)


def run_check(body, tex: str | None = None, **begin) -> tuple[int, str, derivfmt.RunOutput]:
    """Run a check in-process, as a script would: begin, body, finish."""
    out = io.StringIO()
    dc._RUN = None
    code = None
    with contextlib.redirect_stdout(out):
        try:
            dc.begin(tex=tex, script="<test>", **begin)
            body()
            dc.finish()
        except SystemExit as exc:
            code = exc.code
    text = out.getvalue()
    return code, text, derivfmt.RunOutput(text)


def verdicts(run: derivfmt.RunOutput) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for r in run.checks():
        out.setdefault(r["label"], []).append(r["verdict"])
    return out


def check_of(run: derivfmt.RunOutput, label: str, n: int = 0) -> dict:
    return [r for r in run.checks() if r["label"] == label][n]


class TexDir:
    """A temporary folder holding a labeled derivation."""

    def __init__(self, tex: str):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "derivation.tex"
        self.path.write_text(textwrap.dedent(tex))

    def __enter__(self) -> str:
        return str(self.path)

    def __exit__(self, *exc) -> None:
        self.tmp.cleanup()


# --- Gaussian beam symbols, declared as a check script would --------------------


def beam_symbols():
    r = dc.symbol("r", "r", dim="length", nonnegative=True)
    w = dc.symbol("w", "w", dim="length", positive=True)
    return r, w


@needs_sympy
class LaplacianTest(unittest.TestCase):
    """∇²⊥ of e^{−r²/w²} in 2-D polar coordinates is (4r²/w⁴ − 4/w²)·e^{…}."""

    def test_radial_laplacian_is_proved(self) -> None:
        def body():
            r, w = beam_symbols()
            u = dc.exp(-(r**2) / w**2)
            lap = dc.diff(r * dc.diff(u, r), r) / r
            dc.step("step:lap", lap, (4 * r**2 / w**4 - 4 / w**2) * u)

        code, text, run = run_check(body)
        self.assertEqual(code, 0, text)
        rec = check_of(run, "step:lap")
        self.assertEqual(rec["verdict"], "proved-symbolic")
        self.assertIn("needed", rec["assumptions"])
        self.assertEqual(rec["dims"], {"lhs": "length**-2", "rhs": "length**-2"})
        self.assertIn("r", rec["nonzero"])  # 1/r: printed as an assumption of the step
        self.assertEqual(run.problems, [])

    def test_one_dimensional_second_derivative_fails_with_residual(self) -> None:
        def body():
            r, w = beam_symbols()
            u = dc.exp(-(r**2) / w**2)
            dc.step("step:lap", dc.diff(u, r, 2), (4 * r**2 / w**4 - 4 / w**2) * u)

        code, text, run = run_check(body)
        self.assertEqual(code, 1)
        rec = check_of(run, "step:lap")
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertEqual(rec["residual"], "2*exp(-r**2/w**2)/w**2")
        self.assertIn("residual: 2*exp(-r**2/w**2)/w**2", text)
        self.assertEqual(rec["mutants"], {"set": dc.MUTATION_SET, "voided": "the unmutated check failed"})


@needs_sympy
class QParameterTest(unittest.TestCase):
    """q = z + i z_R against 1/q = 1/R(z) − iλ/(π w(z)²)."""

    def check(self, sign):
        def body():
            z = dc.symbol("z", "z", dim="length", positive=True)
            w0 = dc.symbol("w0", "w_0", dim="length", positive=True, convention="waist-1e2@1")
            lam = dc.symbol("lam", r"\lambda", dim="length", positive=True)
            zR = dc.pi * w0**2 / lam
            w2 = w0**2 * (1 + (z / zR) ** 2)
            R = z * (1 + (zR / z) ** 2)
            dc.step("step:q", 1 / (z + sign * dc.I * zR), 1 / R - dc.I * lam / (dc.pi * w2))

        return run_check(body)

    def test_standard_form_is_proved(self) -> None:
        code, text, run = self.check(+1)
        self.assertEqual(code, 0, text)
        self.assertEqual(check_of(run, "step:q")["verdict"], "proved-symbolic")
        self.assertIn("w0 (positive; length; waist-1e2@1)", check_of(run, "step:q")["free_symbols"])

    def test_opposite_sign_of_i_fails(self) -> None:
        code, text, run = self.check(-1)
        self.assertEqual(code, 1)
        self.assertEqual(check_of(run, "step:q")["verdict"], "FAIL")
        self.assertIsNotNone(check_of(run, "step:q")["residual"])


@needs_sympy
class ABCDTest(unittest.TestCase):
    """Free space d, then a thin lens f: M = L(f)·P(d)."""

    def check(self, swapped: bool):
        def body():
            d = dc.symbol("ell", r"\ell", dim="length", positive=True)  # 'd' is reserved
            f = dc.symbol("f", "f", dim="length", positive=True)
            P = dc.Matrix([[1, d], [0, 1]])
            L = dc.Matrix([[1, 0], [-1 / f, 1]])
            composed = P * L if swapped else L * P
            dc.step("step:abcd", composed, dc.Matrix([[1, d], [-1 / f, 1 - d / f]]))

        return run_check(body)

    def test_composition_matches_closed_form(self) -> None:
        code, text, run = self.check(False)
        self.assertEqual(code, 0, text)
        self.assertEqual(check_of(run, "step:abcd")["verdict"], "proved-symbolic")

    def test_swapped_order_fails(self) -> None:
        code, _, run = self.check(True)
        self.assertEqual(code, 1)
        self.assertEqual(check_of(run, "step:abcd")["verdict"], "FAIL")


@needs_sympy
class GouyTest(unittest.TestCase):
    """exp(−i·arctan x) = (1 − ix)/√(1+x²) for real x. Never a silent pass:
    the verdict names what it needed, or says it could not decide."""

    def check(self, sign=-1, **assumptions):
        def body():
            x = dc.symbol("x", "x", dim="1", **assumptions)
            dc.step("step:gouy", dc.exp(sign * dc.I * dc.atan(x)), (1 - dc.I * x) / dc.sqrt(1 + x**2))

        return run_check(body)

    def assert_honest(self, rec: dict) -> None:
        self.assertIn(rec["verdict"], {"proved-symbolic", "numeric-consistent", "inconclusive"})
        if rec["verdict"] == "proved-symbolic":
            self.assertTrue(rec["assumptions"]["needed"])
            self.assertTrue(rec["assumptions"]["declared"])
            self.assertIn("holds", rec["outside_domain"])

    def test_real_x(self) -> None:
        code, text, run = self.check(real=True)
        rec = check_of(run, "step:gouy")
        self.assert_honest(rec)
        self.assertEqual(code, 0, text)

    def test_ratio_of_positive_lengths_names_the_dropped_assumptions(self) -> None:
        # The research note found that simplify() and .equals() cannot decide
        # this with z, z_R positive. Whatever route the helper finds, the
        # verdict states which assumptions the proof needed.
        def body():
            z = dc.symbol("z", "z", dim="length", positive=True)
            zR = dc.symbol("zR", "z_R", dim="length", positive=True)
            dc.step(
                "step:gouy",
                dc.exp(-dc.I * dc.atan(z / zR)),
                (1 - dc.I * z / zR) / dc.sqrt(1 + (z / zR) ** 2),
            )

        code, text, run = run_check(body)
        rec = check_of(run, "step:gouy")
        self.assert_honest(rec)
        if rec["verdict"] == "proved-symbolic":
            self.assertTrue(rec["assumptions"]["needed"].startswith(("none", "z", "zR", "jointly")))

    def test_wrong_sign_fails(self) -> None:
        code, _, run = self.check(sign=+1, real=True)
        self.assertEqual(code, 1)
        self.assertEqual(check_of(run, "step:gouy")["verdict"], "FAIL")


@needs_sympy
class VacuousAndSymbolsTest(unittest.TestCase):
    def test_comparing_an_expression_with_itself_is_vacuous(self) -> None:
        def body():
            r, w = beam_symbols()
            u = dc.exp(-(r**2) / w**2)
            dc.step("step:same", u, u)

        code, text, run = run_check(body)
        self.assertEqual(code, 1)
        self.assertEqual(check_of(run, "step:same")["verdict"], "vacuous")
        self.assertEqual(run.summary()["vacuous"], ["step:same"])

    def test_an_earlier_step_against_itself_is_vacuous(self) -> None:
        def body():
            r, w = beam_symbols()
            dc.step("step:sq", (r + w) ** 2, r**2 + 2 * r * w + w**2)
            dc.step("step:again", "step:sq", "step:sq")

        code, _, run = run_check(body)
        self.assertEqual(check_of(run, "step:again")["verdict"], "vacuous")

    def test_computed_side_equal_to_its_typed_result_is_not_vacuous(self) -> None:
        def body():
            r, w = beam_symbols()
            u = dc.exp(-(r**2) / w**2)
            dc.step("step:du", dc.diff(u, r), -2 * r / w**2 * dc.exp(-(r**2) / w**2))

        code, text, run = run_check(body)
        self.assertEqual(code, 0, text)
        self.assertEqual(check_of(run, "step:du")["verdict"], "proved-symbolic")

    def test_reserved_and_undeclared_symbols(self) -> None:
        dc._RUN = None
        with contextlib.redirect_stdout(io.StringIO()):
            dc.begin(script="<test>")
            with self.assertRaises(dc.CheckError):
                dc.symbol("e")
            dc._RUN = None

        def body():
            r, w = beam_symbols()
            stray = sympy.Symbol("k")  # never declared
            dc.step("step:k", stray * r, r * stray)

        code, _, run = run_check(body)
        rec = check_of(run, "step:k")
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertIn("not in the symbol table", rec["reason"])

    def test_same_name_other_assumptions_is_caught(self) -> None:
        def body():
            r, w = beam_symbols()
            other_w = sympy.Symbol("w")  # no assumptions: not the table's w
            dc.step("step:w", other_w, other_w * 1)

        code, _, run = run_check(body)
        self.assertIn("not the table's w", check_of(run, "step:w")["reason"])

    def test_strings_are_not_parsed(self) -> None:
        dc._RUN = None
        with contextlib.redirect_stdout(io.StringIO()):
            dc.begin(script="<test>")
            dc.symbol("x", real=True)
            with self.assertRaises(dc.CheckError):
                dc.step("step:s", "x**2", "x*x")
            dc._RUN = None


@needs_sympy
class DimensionsTest(unittest.TestCase):
    def test_exp_of_a_length_is_rejected(self) -> None:
        def body():
            L = dc.symbol("L", "L", dim="length", positive=True)
            dc.dims("step:exp", dc.exp(L), "1")

        code, text, run = run_check(body)
        self.assertEqual(code, 1)
        rec = check_of(run, "step:exp")
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertIn("argument of exp has dimension length", rec["reason"])

    def test_exp_of_one_metre_is_rejected(self) -> None:
        from sympy.physics.units import meter

        def body():
            dc.symbol("x", "x", dim="1", real=True)
            dc.dims("step:exp", dc.exp(1 * meter), "1")

        code, _, run = run_check(body)
        self.assertEqual(code, 1)
        self.assertEqual(check_of(run, "step:exp")["verdict"], "FAIL")

    def test_gaussian_profile_is_dimensionless_and_curvature_phase_too(self) -> None:
        def body():
            r, w = beam_symbols()
            k = dc.symbol("k", "k", dim="1/length", positive=True)
            R = dc.symbol("R", "R", dim="length", positive=True)
            dc.dims("step:profile", dc.exp(-(r**2) / w**2), "1")
            dc.dims("step:phase", dc.exp(dc.I * k * r**2 / (2 * R)), "1")

        code, text, run = run_check(body)
        self.assertEqual(code, 0, text)
        self.assertEqual(check_of(run, "step:profile")["verdict"], "dims-only")
        self.assertEqual(check_of(run, "step:phase")["verdict"], "dims-only")
        self.assertGreater(check_of(run, "step:profile")["mutants"]["killed"], 0)

    def test_wrong_power_in_exponent_fails(self) -> None:
        def body():
            r, w = beam_symbols()
            dc.dims("step:profile", dc.exp(-(r**2) / w), "1")

        code, _, run = run_check(body)
        self.assertEqual(code, 1)

    def test_step_checks_dimensions_of_both_sides(self) -> None:
        def body():
            r, w = beam_symbols()
            dc.step("step:mixed", r + w, r + w**2)

        code, _, run = run_check(body)
        rec = check_of(run, "step:mixed")
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertIn("dimension", rec["reason"])


@needs_sympy
class VerdictLinesTest(unittest.TestCase):
    def body(self):
        r, w = beam_symbols()
        dc.step("step:sq", (r + w) ** 2, r**2 + 2 * r * w + w**2)

    def test_untouched_output_reads_clean(self) -> None:
        code, text, run = run_check(self.body)
        self.assertEqual(code, 0, text)
        self.assertEqual(run.problems, [])
        self.assertIsNotNone(run.summary())
        header = run.header
        for key in ("python", "sympy", "mpmath", "pint", "helper", "linter", "mutation_set", "seed"):
            self.assertIn(key, header)
        # Every helper line, human or JSON, carries the run's nonce.
        for line in text.splitlines():
            self.assertTrue(line.startswith(f"[dc:{run.nonce}]") or f'"run":"{run.nonce}"' in line, line)

    def test_edited_verdict_is_detected(self) -> None:
        _, text, _ = run_check(self.body)
        forged = text.replace('"verdict":"proved-symbolic"', '"verdict":"formal"')
        self.assertTrue(any("not written by the helper" in p for p in derivfmt.RunOutput(forged).problems))

    def test_hand_written_verdict_is_detected(self) -> None:
        _, text, _ = run_check(self.body)
        added = text + "step:extra PASS\n"
        self.assertTrue(any("did not write" in p for p in derivfmt.RunOutput(added).problems))

    def test_line_from_another_run_is_detected(self) -> None:
        _, a, _ = run_check(self.body)
        _, b, run_b = run_check(self.body)
        foreign = [line for line in a.splitlines() if line.startswith('{"') and '"check"' in line][0]
        spliced = b.replace(b.splitlines()[-1], foreign + "\n" + b.splitlines()[-1])
        self.assertTrue(any("another run" in p for p in derivfmt.RunOutput(spliced).problems))

    def test_two_runs_compare_equal(self) -> None:
        _, a, _ = run_check(self.body)
        _, b, _ = run_check(self.body)
        self.assertNotEqual(a, b)  # different nonces
        self.assertEqual(derivfmt.comparable(a), derivfmt.comparable(b))


def waist_symbols():
    z = dc.symbol("z", "z", dim="length", positive=True)
    zR = dc.symbol("zR", "z_R", dim="length", positive=True)
    w0 = dc.symbol("w0", "w_0", dim="length", positive=True)
    return z, zR, w0


@needs_sympy
class MutantsTest(unittest.TestCase):
    def test_kills_are_reported_per_step(self) -> None:
        def body():
            r, w = beam_symbols()
            u = dc.exp(-(r**2) / w**2)
            dc.step("step:lap", dc.diff(r * dc.diff(u, r), r) / r, (4 * r**2 / w**4 - 4 / w**2) * u)

        _, _, run = run_check(body)
        m = check_of(run, "step:lap")["mutants"]
        self.assertEqual(m["set"], dc.MUTATION_SET)
        self.assertGreater(m["total"], 5)
        self.assertEqual(m["killed"], m["total"])

    def test_limit_to_zero_is_vacuous_and_a_leading_coefficient_is_not(self) -> None:
        # Δφ = k g T² → 0 as T → 0 cannot tell k g T² from 2 k g T² or k g T³.
        def body():
            k = dc.symbol("k", "k_{\\mathrm{eff}}", dim="1/length", positive=True)
            g = dc.symbol("g", "g", dim="length/time**2", positive=True)
            T = dc.symbol("T", "T", dim="time", positive=True)
            phase = k * g * T**2
            dc.limit_case("step:to-zero", phase, T, 0, 0)
            dc.limit_case("step:leading", phase / T**2, T, 0, k * g)

        code, text, run = run_check(body)
        self.assertEqual(code, 1)
        weak = check_of(run, "step:to-zero")
        self.assertEqual(weak["verdict"], "vacuous")
        self.assertIn("leading behavior", weak["reason"])
        self.assertTrue(weak["mutants"]["survivors"])
        self.assertEqual(check_of(run, "step:leading")["verdict"], "limit-only")
        self.assertGreater(check_of(run, "step:leading")["mutants"]["killed"], 0)

    def test_survivors_are_listed_for_a_person(self) -> None:
        def body():
            z, zR, w0 = waist_symbols()
            dc.limit_case("step:w0", w0 * dc.sqrt(1 + (z / zR) ** 2), z, 0, w0)

        code, text, run = run_check(body)
        self.assertEqual(code, 0, text)
        m = check_of(run, "step:w0")["mutants"]
        self.assertGreater(m["killed"], 0)
        self.assertTrue(m["survivors"])
        self.assertIn("survived, for a person to judge", text)

    def test_equivalence_is_decided_by_value_not_structure(self) -> None:
        # SymPy's canonical forms make most equivalent mutants structurally
        # identical, and those are dropped before counting; the rest are
        # recognized by value and not counted as survivors.
        dc._RUN = None
        with contextlib.redirect_stdout(io.StringIO()):
            dc.begin(script="<test>")
            y = dc.symbol("y", "y", dim="1", real=True)
            run = dc._RUN
            self.assertTrue(dc._equivalent(run, "t", dc.sin(y) ** 2, 1 - dc.cos(y) ** 2))
            self.assertFalse(dc._equivalent(run, "t", y, 2 * y))
            dc._RUN = None

    def test_mutants_can_be_switched_off_and_say_so(self) -> None:
        def body():
            r, w = beam_symbols()
            dc.step("step:sq", (r + w) ** 2, r**2 + 2 * r * w + w**2)

        _, text, run = run_check(body, mutants=False)
        self.assertIsNone(check_of(run, "step:sq")["mutants"])
        self.assertIn("mutants: not run", text)
        self.assertFalse(run.header["mutants"])

    def test_against_substitutes_the_claimed_side(self) -> None:
        def body():
            r, w = beam_symbols()
            dc.step("step:sq", (r + w) ** 2, r**2 + 2 * r * w + w**2)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "against.json"
            path.write_text(json.dumps({"step:sq": "r**2 + r*w + w**2"}))
            import os

            os.environ["DERIVCHECK_AGAINST"] = str(path)
            try:
                code, text, run = run_check(body)
            finally:
                del os.environ["DERIVCHECK_AGAINST"]
        self.assertEqual(code, 1)
        rec = check_of(run, "step:sq")
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertTrue(rec["against"])
        self.assertEqual(rec["residual"], "r*w")
        self.assertIn("step:sq", run.header["against"])


@needs_sympy
class SymbolTableTest(unittest.TestCase):
    def test_needed_assumptions_and_the_point_outside_the_domain(self) -> None:
        def body():
            x = dc.symbol("x", "x", dim="1", positive=True)
            y = dc.symbol("y", "y", dim="1", positive=True)
            dc.step("step:log", dc.log(x * y), dc.log(x) + dc.log(y))

        code, text, run = run_check(body)
        self.assertEqual(code, 0, text)
        rec = check_of(run, "step:log")
        self.assertEqual(rec["verdict"], "proved-symbolic")
        self.assertEqual(rec["assumptions"]["declared"], {"x": ["positive"], "y": ["positive"]})
        self.assertIn("x (positive", rec["assumptions"]["needed"])
        self.assertTrue(rec["outside_domain"]["holds"].startswith("no"))

    def test_denominators_are_printed_as_conditions(self) -> None:
        def body():
            y = dc.symbol("y", "y", dim="1", real=True)
            dc.step("step:frac", (y**2 - 1) / (y - 1), y + 1)

        _, _, run = run_check(body)
        self.assertEqual(check_of(run, "step:frac")["nonzero"], ["y - 1"])

    def test_branch_cuts_are_noted(self) -> None:
        def body():
            s = dc.symbol("s", "s", dim="1")  # complex: no assumptions
            dc.step("step:root", dc.sqrt(1 / s), 1 / dc.sqrt(s))  # wrong on the negative real axis

        code, text, run = run_check(body)
        rec = check_of(run, "step:root")
        # The sampler puts a point on the negative real axis, where the two differ.
        self.assertEqual(rec["verdict"], "FAIL", text)
        self.assertEqual(code, 1)

    def test_branch_notes_on_a_step_that_holds(self) -> None:
        def body():
            s = dc.symbol("s", "s", dim="1")
            dc.step("step:root", dc.sqrt(s) ** 3, s * dc.sqrt(s))

        code, text, run = run_check(body)
        rec = check_of(run, "step:root")
        self.assertEqual(code, 0, text)
        self.assertTrue(any("principal branch" in n for n in rec["notes"]), text)

    def test_operators_do_not_commute(self) -> None:
        def body():
            A = dc.symbol("A", r"\\hat A", kind="operator")
            B = dc.symbol("B", r"\\hat B", kind="operator")
            dc.step("step:right", (A + B) ** 2, A**2 + A * B + B * A + B**2)
            dc.step("step:commuted", (A + B) ** 2, A**2 + 2 * A * B + B**2)

        _, text, run = run_check(body)
        self.assertEqual(check_of(run, "step:right")["verdict"], "proved-symbolic")
        wrong = check_of(run, "step:commuted")
        self.assertEqual(wrong["verdict"], "inconclusive", text)
        self.assertIn("commutators", wrong["method"])

    def test_convention_and_kind_are_validated(self) -> None:
        dc._RUN = None
        with contextlib.redirect_stdout(io.StringIO()):
            dc.begin(script="<test>")
            with self.assertRaises(dc.CheckError):
                dc.symbol("w0", convention="waist")
            with self.assertRaises(dc.CheckError):
                dc.symbol("M", kind="tensor")
            with self.assertRaises(dc.CheckError):
                dc.symbol("v", dim="furlongs")
            dc.symbol("w0", convention="waist-1e2@1")
            with self.assertRaises(dc.CheckError):
                dc.symbol("w0")
            dc._RUN = None

    def test_uses_takes_the_earlier_result_and_flags_retyping(self) -> None:
        def body():
            r, w = beam_symbols()
            u = dc.exp(-(r**2) / w**2)
            dc.step("step:du", dc.diff(u, r), -2 * r / w**2 * u)
            du = dc.result("step:du")
            dc.step("step:d2u", dc.diff(du, r), (4 * r**2 / w**4 - 2 / w**2) * u, uses=["step:du"])
            dc.step("step:retyped", dc.diff(-2 * r / w**2 * u, r), (4 * r**2 / w**4 - 2 / w**2) * u, uses=["step:du"])

        dc._RUN = None
        _, text, run = run_check(body)
        self.assertEqual(check_of(run, "step:d2u")["alarms"], [])
        self.assertEqual(check_of(run, "step:d2u")["uses"], ["step:du"])
        self.assertTrue(any("re-typed" in a for a in check_of(run, "step:retyped")["alarms"]))


@needs_sympy
class IdenticalAsBuiltTest(unittest.TestCase):
    """The alarm for sides SymPy made identical before any check ran fires
    when both look written down, not when a side is computed."""

    def alarmed(self, body) -> dict[str, bool]:
        code, text, run = run_check(body)
        return {r["label"]: any("identical as built" in a for a in r["alarms"]) for r in run.checks()}

    def test_computed_sides_raise_no_alarm(self) -> None:
        def body():
            r, w = beam_symbols()
            ell = dc.symbol("ell", r"\\ell", dim="length", positive=True)
            f = dc.symbol("f", "f", dim="length", positive=True)
            u = dc.exp(-(r**2) / w**2)
            dc.step("step:diff", dc.diff(u, r), -2 * r / w**2 * dc.exp(-(r**2) / w**2))
            du = dc.diff(u, r)
            dc.step("step:named", du, -2 * r / w**2 * dc.exp(-(r**2) / w**2))
            P = dc.Matrix([[1, ell], [0, 1]])
            L = dc.Matrix([[1, 0], [-1 / f, 1]])
            dc.step("step:abcd", L * P, dc.Matrix([[1, ell], [-1 / f, 1 - ell / f]]))
            g = dc.step("step:g", (r + w) ** 2 - w**2, r**2 + 2 * r * w)
            dc.step("step:built", g * w, (r**2 + 2 * r * w) * w)
            dc.step("step:marked", r * w, w * r, computed="lhs")

        self.assertEqual(self.alarmed(body), {
            "step:diff": False, "step:named": False, "step:abcd": False,
            "step:g": False, "step:built": False, "step:marked": False,
        })

    def test_written_down_copies_still_raise_it(self) -> None:
        def body():
            a = dc.symbol("a", "a", dim="1", real=True)
            b = dc.symbol("b", "b", dim="1", real=True)
            x = dc.symbol("x", "x", dim="1", positive=True)
            dc.step("step:copy", a * b, b * a)
            a_plus_b = a + b  # independent of step:copy's result
            dc.step("step:copy-named", a_plus_b, b + a)
            dc.step("step:sqrt", dc.sqrt(x**2), x)  # positivity used while building

        self.assertEqual(self.alarmed(body), {"step:copy": True, "step:copy-named": True, "step:sqrt": True})

    def test_the_worked_example_raises_none(self) -> None:
        text = (Path(__file__).resolve().parent / "fixtures" / "formalize-derivation" / "claims"
                / "2026-10-13-gaussian-beam-paraxial-mode-checks" / "evidence" / "04-output.txt").read_text()
        self.assertNotIn("identical as built", text)


@needs_sympy
class UsesTest(unittest.TestCase):
    """A use is what an expression contains, not what was fetched at some point."""

    def test_a_result_used_through_the_returned_value_needs_no_fetch(self) -> None:
        def body():
            r, w = beam_symbols()
            g = dc.step("step:g", (r + w) ** 2 - w**2, r**2 + 2 * r * w)
            dc.step("step:g2", g / r, r + 2 * w, uses=["step:g"])

        _, text, run = run_check(body)
        self.assertEqual(check_of(run, "step:g2")["alarms"], [], text)

    def test_an_earlier_fetch_does_not_cover_a_later_retyped_step(self) -> None:
        def body():
            r, w = beam_symbols()
            dc.step("step:g", (r + w) ** 2 - w**2, r**2 + 2 * r * w)
            g = dc.result("step:g")
            dc.step("step:first", g * w, r**2 * w + 2 * r * w**2, uses=["step:g"])
            # Re-typed in another form: what a re-typing typo would also look like.
            dc.step("step:later", (r * (r + 2 * w)) / r, r + 2 * w, uses=["step:g"])

        _, text, run = run_check(body)
        self.assertEqual(check_of(run, "step:first")["alarms"], [], text)
        self.assertTrue(any("re-typed" in a for a in check_of(run, "step:later")["alarms"]), text)

    def test_undeclared_uses_are_found_and_reach_the_export(self) -> None:
        def body():
            r, w = beam_symbols()
            k = dc.symbol("k", "k", dim="1/length", positive=True)
            dc.limit_case("step:edge", dc.exp(-(r**2) / w**2), r, dc.oo, 0)
            phase = dc.step("step:phase", k * r**2 / 2 + k * w**2 / 2, k * (r**2 + w**2) / 2)
            dc.dims("step:phase-dims", phase, "length")
            dc.step("step:square", phase**2, k**2 * (r**2 + w**2) ** 2 / 4)
            dc.export("squared", "step:square")

        code, text, run = run_check(body)
        rec = check_of(run, "step:square")
        self.assertEqual(rec["uses"], ["step:phase"], text)
        self.assertEqual(rec["uses_inferred"], ["step:phase"])
        self.assertIn("step:phase (found in the expression)", text)
        self.assertEqual(check_of(run, "step:phase-dims")["uses_inferred"], ["step:phase"])
        export = run.exports()[0]["record"]
        self.assertEqual(set(export["path"]), {"step:square", "step:phase"})


@needs_sympy
class ExportNudgeTest(unittest.TestCase):
    def test_a_run_without_an_export_names_the_step_to_export(self) -> None:
        def body():
            r, w = beam_symbols()
            dc.step("step:a", (r + w) ** 2, r**2 + 2 * r * w + w**2)
            dc.step("step:b", (r - w) ** 2, r**2 - 2 * r * w + w**2)
            dc.limit_case("step:c", (r + w) ** 2 / r**2, r, dc.oo, 1)

        code, text, run = run_check(body)
        self.assertEqual(code, 0)
        self.assertEqual(run.summary()["unexported"], "step:b")
        self.assertIn("nothing is exported", text)

    def test_no_nudge_with_an_export_or_without_a_result(self) -> None:
        def body():
            r, w = beam_symbols()
            dc.step("step:a", (r + w) ** 2, r**2 + 2 * r * w + w**2)
            dc.export("square", "step:a")

        _, _, run = run_check(body)
        self.assertIsNone(run.summary()["unexported"])

        def only_dims():
            r, w = beam_symbols()
            dc.dims("step:d", r / w, "1")

        _, _, run = run_check(only_dims)
        self.assertIsNone(run.summary()["unexported"])


@needs_sympy
class UncheckedTest(unittest.TestCase):
    def test_an_approximation_left_unchecked_raises_an_alarm(self) -> None:
        def body():
            dc.symbol("x", "x", dim="1", real=True)
            dc.unchecked("step:approx", "prose", "set the coupling to 1: first-order perturbation theory")
            dc.unchecked("step:neglect", "prose", "we neglect the second term")
            dc.unchecked("step:def", "definition", "the trial field")
            dc.unchecked("step:words", "prose", "by symmetry the integral vanishes")

        code, _, run = run_check(body)
        self.assertEqual(code, 0)
        self.assertTrue(check_of(run, "step:approx")["alarms"])
        self.assertTrue(check_of(run, "step:neglect")["alarms"])
        self.assertEqual(check_of(run, "step:def")["alarms"], [])
        self.assertEqual(check_of(run, "step:words")["alarms"], [])
        self.assertIn("series_step", check_of(run, "step:approx")["alarms"][0])


@needs_sympy
class SeriesTest(unittest.TestCase):
    """Near the waist, w(z) = w0 √(1 + z²/z_R²) ≈ w0 (1 + z²/(2 z_R²))."""

    def series(self, approx_of, order, point=0, tex=None):
        def body():
            z, zR, w0 = waist_symbols()
            w = w0 * dc.sqrt(1 + (z / zR) ** 2)
            dc.series_step("step:near", w, approx_of(z, zR, w0), z, order, point=point)

        return run_check(body, tex=tex)

    def test_near_waist_expansion_is_verified_with_its_next_term(self) -> None:
        code, text, run = self.series(lambda z, zR, w0: w0 * (1 + z**2 / (2 * zR**2)), 3)
        self.assertEqual(code, 0, text)
        rec = check_of(run, "step:near")
        self.assertEqual(rec["verdict"], "series-verified")
        self.assertEqual(rec["next_term"], "-w0*z**4/(8*zR**4)")
        self.assertIn("shrinks like", rec["scaling"])
        self.assertGreater(rec["mutants"]["killed"], 0)

    def test_claim_too_coarse_for_its_own_O_term_is_rejected(self) -> None:
        # SymPy turns w0 (1 + z²/(2 z_R²)) + O(z²) into w0 + O(z²): the z² term,
        # the whole content of the claim, is gone before anything is compared.
        code, text, run = self.series(lambda z, zR, w0: w0 * (1 + z**2 / (2 * zR**2)) + dc.O(z**2), 2)
        self.assertEqual(code, 1)
        rec = check_of(run, "step:near")
        self.assertEqual(rec["verdict"], "vacuous")
        self.assertIn("O(z**2)", rec["reason"])

    def test_O_term_of_the_right_order_is_accepted(self) -> None:
        code, text, run = self.series(lambda z, zR, w0: w0 * (1 + z**2 / (2 * zR**2)) + dc.O(z**4), 3)
        self.assertEqual(code, 0, text)
        self.assertEqual(check_of(run, "step:near")["verdict"], "series-verified")

    def test_O_term_that_does_not_match_the_order_fails(self) -> None:
        code, _, run = self.series(lambda z, zR, w0: w0 * (1 + z**2 / (2 * zR**2)) + dc.O(z**4), 2)
        self.assertEqual(check_of(run, "step:near")["verdict"], "FAIL")

    def test_wrong_coefficient_fails_with_the_difference(self) -> None:
        code, _, run = self.series(lambda z, zR, w0: w0 * (1 + z**2 / zR**2), 3)
        self.assertEqual(code, 1)
        rec = check_of(run, "step:near")
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertEqual(rec["residual"], "-w0*z**2/(2*zR**2)")

    def test_far_field_at_infinity(self) -> None:
        code, text, run = self.series(lambda z, zR, w0: w0 * z / zR + w0 * zR / (2 * z), 2, point=dc.oo)
        self.assertEqual(code, 0, text)
        rec = check_of(run, "step:near")
        self.assertEqual(rec["verdict"], "series-verified")
        self.assertEqual(rec["next_term"], "-w0*zR**3/(8*z**3)")

    def test_an_approximation_written_as_equals_raises_an_alarm(self) -> None:
        with TexDir(r"""
            \begin{equation}
              w(z) = w_0\left(1 + \frac{z^2}{2 z_R^2}\right) \label{step:near}
            \end{equation}
        """) as tex:
            _, _, run = self.series(lambda z, zR, w0: w0 * (1 + z**2 / (2 * zR**2)), 3, tex=tex)
        self.assertTrue(any("'='" in a for a in check_of(run, "step:near")["alarms"]))

    def test_an_identity_check_of_an_approx_step_raises_an_alarm(self) -> None:
        with TexDir(r"""
            \begin{equation}
              w(z) \approx w_0 \label{step:w}
            \end{equation}
        """) as tex:
            def body():
                z, zR, w0 = waist_symbols()
                dc.step("step:w", w0 * (1 + z - z), w0)

            _, _, run = run_check(body, tex=tex)
        self.assertTrue(any("≈" in a for a in check_of(run, "step:w")["alarms"]))


class TexStepsTest(unittest.TestCase):
    def test_align_rows_and_comments(self) -> None:
        tex = textwrap.dedent(r"""
            % \label{step:commented}
            \begin{align}
              u &= e^{-r^2/w^2} \label{step:gauss} \\
              \nabla^2 u &= 0 \label{step:lap} \nonumber
            \end{align}
            \begin{equation}
              q = z + i z_R \label{step:q}
            \end{equation}
        """)
        self.assertEqual(derivfmt.tex_labels(tex), ["step:gauss", "step:lap", "step:q"])
        steps = derivfmt.tex_steps(tex)
        self.assertEqual(steps["step:gauss"], "u &= e^{-r^2/w^2}")
        self.assertEqual(steps["step:lap"], r"\nabla^2 u &= 0")
        self.assertEqual(steps["step:q"], "q = z + i z_R")


class LinterTest(unittest.TestCase):
    CLEAN = textwrap.dedent('''
        # /// script
        # requires-python = ">=3.10"
        # dependencies = ["sympy==1.14.0", "mpmath==1.3.0", "pint==0.24.4"]
        # ///
        import derivcheck as dc

        dc.begin(tex="02-derivation.tex")
        r = dc.symbol("r", "r", dim="length", nonnegative=True)
        w = dc.symbol("w", "w", dim="length", positive=True)
        u = dc.exp(-r**2 / w**2)
        dc.step("step:lap", dc.diff(r * dc.diff(u, r), r) / r, (4*r**2/w**4 - 4/w**2) * u)
        print("intermediate:", u)
        dc.finish()
    ''')

    def rules(self, source: str) -> set[str]:
        return {v.rule for v in derivlint.lint(source)}

    def test_clean_script(self) -> None:
        self.assertEqual(derivlint.lint(self.CLEAN), [])
        self.assertTrue(derivlint.has_inline_metadata(self.CLEAN))

    def test_script_printing_its_own_pass_fails_the_lint(self) -> None:
        bad = self.CLEAN.replace('print("intermediate:", u)', 'print("step:lap PASS")')
        self.assertIn("prints-verdict", self.rules(bad))
        bad = self.CLEAN.replace('print("intermediate:", u)', 'print(f"{u} verified ✓")')
        self.assertIn("prints-verdict", self.rules(bad))

    def test_each_rule(self) -> None:
        cases = {
            "try-around-helper": "try:\n    dc.step('step:x', u, u)\nexcept Exception:\n    pass",
            "assert-true": "assert True",
            "eq-compare": "ok = dc.simplify(u - u) == 0",
            "no-tolerance": "import math\nmath.isclose(1.0, 1.0)",
            "numbers-first": "v = u.subs(r, 0.5)",
            "monkeypatch": "dc.step = lambda *a, **k: None",
            "own-exit": "import sys\nsys.exit(0)",
        }
        for rule, snippet in cases.items():
            with self.subTest(rule=rule):
                bad = self.CLEAN.replace('print("intermediate:", u)', snippet)
                self.assertIn(rule, self.rules(bad))

    def test_stated_tolerance_and_string_compare_are_fine(self) -> None:
        ok = self.CLEAN.replace(
            'print("intermediate:", u)',
            'import math\nmath.isclose(1.0, 1.0, rel_tol=1e-12)\nif __name__ == "__main__":\n    pass',
        )
        self.assertEqual(self.rules(ok), set())

    def test_missing_finish(self) -> None:
        self.assertIn("no-finish", self.rules(self.CLEAN.replace("dc.finish()", "")))

    def test_from_import_and_monkeypatch(self) -> None:
        src = "from derivcheck import begin, step, finish\nbegin()\nstep = None\nfinish()\n"
        self.assertIn("monkeypatch", self.rules(src))
        src = "import derivcheck as dc\nfrom derivcheck import _cascade\ndc.begin()\ndc.finish()\n"
        self.assertIn("monkeypatch", self.rules(src))


if __name__ == "__main__":
    unittest.main()
