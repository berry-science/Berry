"""derivcheck — the helper a derivation's check script runs through.

A check script declares its symbols once, states each step of the
derivation as SymPy expressions, and hands every comparison to this module.
Only this module writes verdicts. The script never decides PASS or FAIL
itself, and the coverage check refuses one that tries (see derivlint.py).

    import derivcheck as dc

    dc.begin(tex="02-derivation.tex", seed=20261013)
    r = dc.symbol("r", r"r", dim="length", nonnegative=True)
    w = dc.symbol("w", r"w", dim="length", positive=True)
    u = dc.exp(-r**2 / w**2)
    lap = dc.diff(r * dc.diff(u, r), r) / r
    dc.step("step:laplacian", lap, (4 * r**2 / w**4 - 4 / w**2) * u)
    dc.finish()

Verdicts, strongest first: proved-symbolic and series-verified, exact-finite,
numeric-consistent, limit-only, dims-only; then inconclusive, unchecked,
vacuous and FAIL. Numeric agreement is never reported as proved. A check
that no generated mutant can fail is reported as vacuous, never as a pass.
`finish()` exits non-zero on any FAIL or vacuous verdict.

Needs SymPy and mpmath; pint is used for a second, numeric dimension check
when it is installed. Run a script with `formalize.py run <claim-id>`,
which uses `uv run` and the script's inline dependencies where uv is
available.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import platform
import random
import re as _regex  # `re` is SymPy's real part, re-exported below
import secrets
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable

import mpmath
import sympy as sp
from sympy import (  # noqa: F401  re-exported so a script needs one import
    Abs,
    E,
    Eq,
    Function,
    I,
    Integral,
    Matrix,
    Piecewise,
    Rational,
    S,
    acos,
    asin,
    atan,
    atan2,
    besselj,
    cos,
    cosh,
    diff,
    exp,
    integrate,
    log,
    oo,
    O,
    pi,
    re,
    im,
    conjugate,
    sin,
    sinh,
    sqrt,
    tan,
    tanh,
)
from sympy.physics.units.systems.si import SI, dimsys_SI
from sympy.physics.units.quantities import Quantity

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import derivfmt  # noqa: E402
import derivlint  # noqa: E402

HELPER_VERSION = "0.1.0"
MUTATION_SET = "m0.1"  # ×2, sign of a term, i→−i, power ±1, s→s², drop a term, swap same-dimension symbols

FORBIDDEN_NAMES = {
    "e", "E", "i", "I", "pi", "oo", "d", "dx", "dy", "dz", "dt", "partial",
    "nabla", "mathrm", "frac", "left", "right", "approx", "vec", "hat",
}
KINDS = {"scalar", "operator", "matrix", "function"}
ASSUMPTION_KEYS = {
    "positive", "negative", "nonnegative", "nonpositive", "nonzero", "real",
    "integer", "rational", "finite", "imaginary", "complex", "extended_real",
    "zero", "even", "odd", "prime",
}

# Words that say a step approximates: such a step is checked against what it
# approximates, not left unchecked.
APPROXIMATION_WORDS = _regex.compile(
    r"approx|≈|\\simeq|neglect|truncat|perturbati|expansion|"
    r"\b(first|second|leading|lowest|higher)[- ]order\b|\bto (first|leading|lowest) order\b|"
    r"\bdrop(s|ped|ping)?\b|\bset\b[^.;]*(=|\bto\b)|\bsmall[- ]\w+",
    _regex.IGNORECASE,
)

DEFAULT_SEED = 1
DEFAULT_DPS = 30
DEFAULT_POINTS = 5
DEFAULT_TIMEOUT = 10.0
MAX_MUTANTS = 16


class CheckError(Exception):
    """A misuse of the helper: said plainly, before any verdict is written."""


class _Timeout(Exception):
    pass


@contextlib.contextmanager
def _deadline(seconds: float | None):
    usable = (
        seconds
        and hasattr(signal, "SIGALRM")
        and threading.current_thread() is threading.main_thread()
    )
    if not usable:
        yield
        return

    def _raise(signum, frame):  # noqa: ARG001
        raise _Timeout()

    old = signal.signal(signal.SIGALRM, _raise)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def _timed(fn: Callable[[], Any], seconds: float | None) -> Any:
    """fn(), or None if it ran out of time or raised."""
    try:
        with _deadline(seconds):
            return fn()
    except _Timeout:
        return None
    except Exception:  # noqa: BLE001 — a SymPy failure is an inconclusive step, not a crash
        return None


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _version(module: str) -> str | None:
    try:
        return __import__(module).__version__
    except Exception:  # noqa: BLE001
        return None


# --- dimensions ---------------------------------------------------------------------

_DIM_NAMES: dict[str, Any] = {}
SI_BASE = {"length", "mass", "time", "current", "temperature", "amount_of_substance", "luminous_intensity"}


def _dim_namespace() -> dict[str, Any]:
    if not _DIM_NAMES:
        from sympy.physics.units import dimensions as D
        from sympy.physics.units.definitions import dimension_definitions as DD

        for module in (D, DD):
            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, D.Dimension):
                    _DIM_NAMES[name] = obj
        _DIM_NAMES["amount"] = _DIM_NAMES.get("amount_of_substance")
        _DIM_NAMES["luminosity"] = _DIM_NAMES.get("luminous_intensity")
    return _DIM_NAMES


def _deps(dimension: Any) -> dict[str, sp.Rational]:
    raw = dimsys_SI.get_dimensional_dependencies(dimension)
    return {str(k.name): sp.Rational(v) for k, v in raw.items() if v != 0}


def parse_dim(text: Any) -> dict[str, sp.Rational]:
    """'length/time**2' -> {'length': 1, 'time': -2}; '1' -> {} (dimensionless)."""
    from sympy.physics.units.dimensions import Dimension

    if isinstance(text, dict):
        return {k: sp.Rational(v) for k, v in text.items() if v != 0}
    if isinstance(text, Dimension):
        return _deps(text)
    if text in (1, "1", "dimensionless", "none", ""):
        return {}
    if not isinstance(text, str):
        raise CheckError(f"dimension {text!r}: give it as a string like 'length/time'")
    try:
        value = sp.sympify(text, locals=_dim_namespace())
    except (sp.SympifyError, TypeError, SyntaxError) as exc:
        raise CheckError(f"dimension {text!r} could not be read: {exc}") from None
    if value == 1:
        return {}
    if not isinstance(value, Dimension):
        value = Dimension(value)
    try:
        deps = _deps(value)
    except Exception:  # noqa: BLE001
        deps = None
    if deps is None or not set(deps) <= SI_BASE:
        raise CheckError(
            f"dimension {text!r} is not built from SI dimensions "
            "(length, mass, time, current, temperature, amount, luminosity, or derived "
            "ones such as velocity, energy, frequency)"
        )
    return deps


def dim_str(d: dict[str, Any] | None) -> str | None:
    if d is None:
        return None
    if not d:
        return "1"
    parts = []
    for name in sorted(d):
        p = sp.Rational(d[name])
        parts.append(name if p == 1 else f"{name}**{p}" if p.q == 1 else f"{name}**({p})")
    return "*".join(parts)


class _DimError(Exception):
    """The expression's dimensions are inconsistent."""


class _DimUnknown(Exception):
    """Some symbol has no declared dimension."""


_PASSTHROUGH = (sp.Abs, sp.re, sp.im, sp.conjugate, sp.Max, sp.Min)


def _add_dims(a: dict, b: dict, k: Any = 1) -> dict:
    out = dict(a)
    for name, p in b.items():
        out[name] = out.get(name, 0) + k * p
        if out[name] == 0:
            del out[name]
    return out


# --- the symbol table -----------------------------------------------------------------


class Entry:
    def __init__(self, name, latex, kind, dim, assumptions, convention, obj, shape=None):
        self.name = name
        self.latex = latex
        self.kind = kind
        self.dim = dim  # dict or None
        self.assumptions = assumptions  # the declared ones, as given
        self.convention = convention
        self.obj = obj
        self.shape = shape

    def record(self) -> dict[str, Any]:
        out = {
            "name": self.name,
            "latex": self.latex,
            "kind": self.kind,
            "assumptions": sorted(k for k, v in self.assumptions.items() if v)
            + sorted(f"not {k}" for k, v in self.assumptions.items() if v is False),
            "dim": dim_str(self.dim),
            "convention": self.convention,
        }
        if self.shape:
            out["shape"] = list(self.shape)
        return out

    def describe(self) -> str:
        bits = [", ".join(self.record()["assumptions"]) or "no assumptions"]
        if self.dim is not None:
            bits.append(dim_str(self.dim) if self.dim else "dimensionless")
        if self.kind != "scalar":
            bits.append(self.kind)
        if self.convention:
            bits.append(self.convention)
        return f"{self.name} ({'; '.join(bits)})"


# --- a run ---------------------------------------------------------------------------


class _Run:
    def __init__(self, tex, seed, dps, points, mutants, timeout, script, out):
        self.nonce = secrets.token_hex(6)
        self.seq = 0
        self.prev_mac = ""
        self.out = out
        self.started = time.time()
        self.seed = seed
        self.dps = dps
        self.points = points
        self.timeout = timeout
        self.mutants_on = mutants and os.environ.get("DERIVCHECK_MUTANTS", "1") != "0"
        self.table: dict[str, Entry] = {}
        self.by_obj: dict[Any, Entry] = {}
        self.results: dict[str, Any] = {}  # label -> the checked expression a later step may use
        self.fetched: set[str] = set()
        self.fetched_recent: set[str] = set()  # fetched since the last check was written
        self.verdicts: dict[str, list[str]] = {}
        self.kinds: dict[str, str] = {}
        self.used: set[str] = set()
        self.uses: dict[str, list[str]] = {}
        self.exported: list[str] = []
        self.export_names: set[str] = set()
        self.finished = False
        self.script = Path(script).resolve() if script else None
        self.tex_path = None
        self.tex_steps: dict[str, str] = {}
        if tex:
            p = Path(tex)
            if not p.is_absolute():
                base = self.script.parent if self.script else Path.cwd()
                p = base / p
            if not p.is_file():
                raise CheckError(f"the derivation {p} does not exist")
            self.tex_path = p.resolve()
            self.tex_steps = derivfmt.tex_steps(p.read_text(encoding="utf-8"))
        self.against = self._load_against()
        self._header()

    # writing -------------------------------------------------------------

    def human(self, text: str) -> None:
        for line in text.splitlines() or [""]:
            print(f"[{derivfmt.PREFIX}:{self.nonce}] {line}", file=self.out)

    def record(self, obj: dict[str, Any]) -> dict[str, Any]:
        obj = {"derivcheck": obj.pop("derivcheck"), "run": self.nonce, "seq": self.seq, **obj}
        obj["mac"] = derivfmt.mac(self.nonce, self.prev_mac, obj)
        self.prev_mac = obj["mac"]
        self.seq += 1
        print(derivfmt.canonical(obj), file=self.out)
        self.out.flush()
        return obj

    def _header(self) -> None:
        versions = {
            "python": platform.python_version(),
            "sympy": sp.__version__,
            "mpmath": mpmath.__version__,
            "pint": _version("pint"),
        }
        header = {
            "derivcheck": "header",
            "format_version": derivfmt.FORMAT_VERSION,
            "helper": HELPER_VERSION,
            "helper_sha256": _sha256(Path(__file__)),
            "linter": derivlint.LINT_VERSION,
            "mutation_set": MUTATION_SET,
            **versions,
            "seed": self.seed,
            "dps": self.dps,
            "points": self.points,
            "timeout": self.timeout,
            "mutants": self.mutants_on,
            "script": self.script.name if self.script else None,
            "script_sha256": _sha256(self.script),
            "tex": self.tex_path.name if self.tex_path else None,
            "tex_sha256": _sha256(self.tex_path),
            "against": dict(getattr(self, "_against_raw", {})) or None,
            "runner": os.environ.get("DERIVCHECK_RUNNER", "python"),
        }
        self.human(
            f"derivcheck {HELPER_VERSION} (linter {derivlint.LINT_VERSION}, mutations "
            f"{MUTATION_SET}); Python {versions['python']}, SymPy {versions['sympy']}, "
            f"mpmath {versions['mpmath']}, pint {versions['pint'] or 'not installed'}; "
            f"seed {self.seed}, {self.dps} digits, {self.points} points"
        )
        if self.against:
            self.human("AGAINST: steps re-run with substitute expressions: " + ", ".join(self.against))
        self.record(header)

    def _load_against(self) -> dict[str, Any]:
        path = os.environ.get("DERIVCHECK_AGAINST")
        if not path:
            return {}
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise CheckError("DERIVCHECK_AGAINST: a JSON object {label: expression}")
        self._against_raw = data
        return {}  # resolved lazily, once the symbols are declared

    def against_for(self, label: str) -> Any | None:
        raw = getattr(self, "_against_raw", {})
        if label not in raw:
            return None
        names = {e.name: e.obj for e in self.table.values()}
        ns = {**{k: getattr(sp, k) for k in dir(sp) if not k.startswith("_")}, **names}
        value = sp.sympify(raw[label], locals=ns)
        self.against[label] = value
        return value

    # the symbol table ------------------------------------------------------

    def symbol(self, name, latex, dim, kind, convention, shape, assumptions):
        if name in FORBIDDEN_NAMES:
            raise CheckError(
                f"symbol name {name!r} is reserved: it reads as a constant or as LaTeX "
                "debris (use E, I, pi from the helper; name the symbol for what it is)"
            )
        if name in self.table:
            raise CheckError(f"symbol {name!r} is declared twice: declare each symbol once")
        if kind not in KINDS:
            raise CheckError(f"kind {kind!r} is not one of {sorted(KINDS)}")
        unknown = set(assumptions) - ASSUMPTION_KEYS
        if unknown:
            raise CheckError(f"unknown assumptions {sorted(unknown)} for {name!r}")
        if convention is not None and not derivlint.CONVENTION_REF.match(convention):
            raise CheckError(f"convention {convention!r} is not 'key@version'")
        d = parse_dim(dim) if dim is not None else None
        if kind == "scalar":
            obj = sp.Symbol(name, **assumptions)
        elif kind == "operator":
            obj = sp.Symbol(name, commutative=False, **assumptions)
        elif kind == "matrix":
            if not shape or len(shape) != 2:
                raise CheckError(f"matrix {name!r} needs shape=(rows, columns)")
            if assumptions:
                raise CheckError(f"matrix {name!r}: SymPy matrix symbols take no assumptions")
            obj = sp.MatrixSymbol(name, *shape)
        else:
            obj = sp.Function(name, **assumptions)
        entry = Entry(name, latex if latex is not None else name, kind, d, dict(assumptions),
                      convention, obj, shape)
        self.table[name] = entry
        self.by_obj[obj] = entry
        return obj

    def entry_of(self, s: Any) -> Entry | None:
        return self.by_obj.get(s)

    def free(self, *exprs: Any) -> set:
        out: set = set()
        for e in exprs:
            out |= _free_symbols(e)
        return out

    def check_symbols(self, *exprs: Any) -> str | None:
        """None, or why the expressions are not stated in the declared symbols."""
        for s in sorted(self.free(*exprs), key=str):
            if s in self.by_obj:
                continue
            same = self.table.get(str(s))
            if same is not None:
                return (
                    f"symbol {s} is not the table's {s}: it was made with different "
                    "assumptions (use the object dc.symbol returned)"
                )
            if str(s) in FORBIDDEN_NAMES:
                return f"free symbol {s!r}: LaTeX debris or a constant typed as a symbol"
            return f"free symbol {s} is not in the symbol table (declare it with dc.symbol)"
        for f in _undefined_functions(*exprs):
            if f not in self.by_obj:
                return f"function {f} is not in the symbol table (declare it with dc.function)"
        return None

    # dimensions -----------------------------------------------------------

    def dim_of(self, e: Any) -> dict:
        if isinstance(e, sp.MatrixBase):
            raise _DimUnknown("a matrix (its elements may carry different dimensions)")
        if isinstance(e, Quantity):
            return _deps(SI.get_quantity_dimension(e))
        if e.is_Number or e in (sp.I, sp.pi, sp.E) or isinstance(e, sp.NumberSymbol):
            return {}
        if e.is_Symbol:
            entry = self.entry_of(e)
            if entry is None or entry.dim is None:
                raise _DimUnknown(f"{e} has no declared dimension")
            return entry.dim
        if isinstance(e, sp.MatrixSymbol):
            raise _DimUnknown("a matrix symbol")
        if e.is_Add:
            dims = [(t, self.dim_of(t)) for t in e.args]
            first_t, first = dims[0]
            for t, d in dims[1:]:
                if d != first:
                    raise _DimError(
                        f"adds {dim_str(first)} ({sp.sstr(first_t)}) to {dim_str(d)} ({sp.sstr(t)})"
                    )
            return first
        if e.is_Mul:
            out: dict = {}
            for t in e.args:
                out = _add_dims(out, self.dim_of(t))
            return out
        if e.is_Pow:
            db = self.dim_of(e.base)
            de = self.dim_of(e.exp)
            if de:
                raise _DimError(f"exponent {sp.sstr(e.exp)} has dimension {dim_str(de)}")
            if not db:
                return {}
            if not e.exp.is_Rational:
                raise _DimError(
                    f"{sp.sstr(e.base)} has dimension {dim_str(db)} and is raised to the "
                    f"symbolic power {sp.sstr(e.exp)}"
                )
            return {k: v * e.exp for k, v in db.items()}
        if isinstance(e, sp.Derivative):
            out = self.dim_of(e.expr)
            for var, n in e.variable_count:
                out = _add_dims(out, self.dim_of(var), -n)
            return out
        if isinstance(e, sp.Integral):
            out = self.dim_of(e.function)
            for lim in e.limits:
                out = _add_dims(out, self.dim_of(lim[0]))
            return out
        if isinstance(e, sp.Piecewise):
            dims = [self.dim_of(arg.expr) for arg in e.args]
            if any(d != dims[0] for d in dims[1:]):
                raise _DimError("the branches of a Piecewise differ in dimension")
            return dims[0]
        if isinstance(e, _PASSTHROUGH):
            dims = [self.dim_of(a) for a in e.args]
            if any(d != dims[0] for d in dims[1:]):
                raise _DimError(f"{type(e).__name__} of arguments with different dimensions")
            return dims[0]
        if isinstance(e, sp.atan2):
            a, b = (self.dim_of(x) for x in e.args)
            if a != b:
                raise _DimError(f"atan2 of {dim_str(a)} and {dim_str(b)}")
            return {}
        if isinstance(e, sp.DiracDelta):
            return {k: -v for k, v in self.dim_of(e.args[0]).items()}
        if isinstance(e, sp.core.function.AppliedUndef):
            entry = self.entry_of(e.func)
            if entry is None or entry.dim is None:
                raise _DimUnknown(f"function {e.func} has no declared dimension")
            return entry.dim
        if isinstance(e, sp.Function):
            for a in e.args:
                d = self.dim_of(a)
                if d:
                    raise _DimError(
                        f"the argument of {type(e).__name__} has dimension {dim_str(d)}: "
                        f"{sp.sstr(e)}"
                    )
            return {}
        if isinstance(e, sp.Order):
            raise _DimUnknown("an O() term")
        if not e.free_symbols:
            return {}
        raise _DimUnknown(f"no dimension rule for {type(e).__name__}")

    def dims_of_pair(self, lhs, rhs) -> dict[str, Any] | None:
        """For a step: both sides' dimensions, or None if some symbol has none.
        Raises _DimError when they are inconsistent."""
        try:
            dl = self.dim_of(lhs) if not _is_zero(lhs) else None
            dr = self.dim_of(rhs) if not _is_zero(rhs) else None
        except _DimUnknown:
            return None
        if dl is None or dr is None:  # zero carries any dimension
            d = dl if dl is not None else dr
            return {"lhs": dim_str(d), "rhs": dim_str(d)} if d is not None else None
        if dl != dr:
            raise _DimError(f"the two sides differ in dimension: {dim_str(dl)} and {dim_str(dr)}")
        return {"lhs": dim_str(dl), "rhs": dim_str(dr)}

    # sampling ------------------------------------------------------------

    def rng(self, label: str, what: str) -> random.Random:
        return random.Random(f"{self.seed}:{label}:{what}")

    def sample(self, symbols: Iterable, rng: random.Random, outside: bool = False, index: int = 1):
        """Exact (rational) values for the symbols, inside their declared domain —
        or, with outside=True, one point that breaks every declared assumption."""
        point = {}
        broken = []
        for s in sorted(symbols, key=str):
            entry = self.entry_of(s)
            if entry is None or entry.kind != "scalar":
                return None, []
            a = s.assumptions0
            mag = sp.Rational(rng.randint(35, 240), 100)
            if outside:
                if a.get("integer"):
                    point[s] = sp.Rational(1, 2) + (-mag if a.get("positive") or a.get("nonnegative") else 0)
                    broken.append(str(s))
                elif a.get("positive") or a.get("nonnegative"):
                    point[s] = -mag
                    broken.append(str(s))
                elif a.get("negative") or a.get("nonpositive"):
                    point[s] = mag
                    broken.append(str(s))
                elif a.get("real"):
                    point[s] = mag + sp.I * sp.Rational(rng.randint(35, 240), 100)
                    broken.append(str(s))
                elif a.get("nonzero"):
                    point[s] = sp.Integer(0)
                    broken.append(str(s))
                else:
                    point[s] = mag + sp.I * sp.Rational(rng.randint(-240, 240), 100)
                continue
            if a.get("integer"):
                v = sp.Integer(rng.randint(1, 5))
                point[s] = -v if a.get("negative") else v
            elif a.get("positive") or a.get("nonnegative"):
                point[s] = mag
            elif a.get("negative") or a.get("nonpositive"):
                point[s] = -mag
            elif a.get("real") or a.get("extended_real"):
                point[s] = mag if rng.random() < 0.5 else -mag
            elif a.get("imaginary"):
                point[s] = sp.I * mag
            elif index == 0:
                # Complex and unconstrained: the first point sits on the negative
                # real axis, where principal branches (sqrt, log, powers) cut.
                point[s] = -mag
            else:
                sign = 1 if rng.random() < 0.5 else -1
                point[s] = sign * mag + sp.I * sp.Rational(rng.randint(-240, 240), 100)
        return point, broken

    def finish(self) -> int:
        if self.finished:
            raise CheckError("finish() was called twice")
        self.finished = True
        labels = {lab: derivfmt.aggregate(v) for lab, v in self.verdicts.items()}
        alarms: list[str] = []
        notes: list[str] = []
        if self.exported:
            reached = set()
            stack = list(self.exported)
            while stack:
                x = stack.pop()
                if x in reached:
                    continue
                reached.add(x)
                stack.extend(self.uses.get(x, []))
            unused = [
                lab for lab, kind in self.kinds.items()
                if kind in ("step", "series") and lab not in reached and lab not in self.used
            ]
            if unused:
                notes.append("not used by any later step or export: " + ", ".join(unused))
        unexported = None
        if not self.export_names and self.results:
            # The last step that carries a result is the likeliest result of the
            # derivation; a grader or a later claim needs it as data.
            unexported = list(self.results)[-1]
            notes.append(
                f"nothing is exported: export the result with dc.export(\"<name>\", {unexported!r}) "
                "so a grader or a later derivation can point at it"
            )
        fails = sorted(lab for lab, v in labels.items() if v == "FAIL")
        vacuous = sorted(lab for lab, v in labels.items() if v == "vacuous")
        code = 1 if fails or vacuous else 0
        self.human("")
        self.human("summary:")
        for lab, v in labels.items():
            self.human(f"  {lab:<28} {v}")
        for a in alarms:
            self.human(f"  alarm: {a}")
        for n in notes:
            self.human(f"  note: {n}")
        if fails or vacuous:
            self.human(
                f"exit {code}: "
                + "; ".join(x for x in (
                    f"{len(fails)} failed ({', '.join(fails)})" if fails else "",
                    f"{len(vacuous)} vacuous ({', '.join(vacuous)})" if vacuous else "",
                ) if x)
            )
        else:
            self.human("exit 0: no step failed and no check was vacuous")
        self.record({
            "derivcheck": "summary",
            "labels": labels,
            "failed": fails,
            "vacuous": vacuous,
            "alarms": alarms,
            "notes": notes,
            "unexported": unexported,
            "symbols": {e.name: e.record() for e in self.table.values()},
            "exit": code,
            "seconds": round(time.time() - self.started, 2),
        })
        return code


_RUN: _Run | None = None


def _run() -> _Run:
    if _RUN is None:
        raise CheckError("call derivcheck.begin(tex=...) before anything else")
    if _RUN.finished:
        raise CheckError("finish() has been called: nothing is checked after it")
    return _RUN


def _free_symbols(e: Any) -> set:
    if isinstance(e, sp.MatrixBase):
        out: set = set()
        for x in e:
            out |= _free_symbols(x)
        return out
    if isinstance(e, sp.Basic):
        return set(e.free_symbols)
    return set()


def _undefined_functions(*exprs: Any) -> set:
    out = set()
    for e in exprs:
        if isinstance(e, sp.Basic):
            out |= {f.func for f in e.atoms(sp.core.function.AppliedUndef)}
    return out


_SOURCES: dict[str, Any] = {}


def _call_node(frame: Any, function: str):
    """The helper call on the caller's line, in the caller's syntax tree:
    (call node, tree), or None if the source is unavailable."""
    import ast

    filename, line = frame.f_code.co_filename, frame.f_lineno
    if filename not in _SOURCES:
        try:
            _SOURCES[filename] = ast.parse(Path(filename).read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            _SOURCES[filename] = None
    tree = _SOURCES[filename]
    if tree is None:
        return None
    best = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
        if name != function or not (node.lineno <= line <= (node.end_lineno or node.lineno)):
            continue
        if best is None or node.lineno >= best.lineno:
            best = node
    return (best, tree) if best is not None else None


def _compared_arguments(call: Any) -> list:
    args = list(call.args[1:3])
    for kw in call.keywords:
        if kw.arg in ("lhs", "rhs", "exact", "approx"):
            args.append(kw.value)
    return args


def _same_source_arguments(frame: Any, function: str) -> bool | None:
    """Whether the helper call on the caller's line passes the same source
    expression as its two compared arguments; None if the source is unavailable."""
    import ast

    found = _call_node(frame, function)
    if found is None:
        return None
    args = _compared_arguments(found[0])
    if len(args) < 2:
        return None
    return ast.dump(args[0]) == ast.dump(args[1])


# Calls that write an expression down rather than compute one.
_TYPING_CALLS = {
    "symbol", "symbols", "Symbol", "function", "Function", "Rational", "Integer", "Float", "S",
    "Matrix", "ImmutableMatrix", "exp", "log", "sqrt", "sin", "cos", "tan", "asin", "acos",
    "atan", "atan2", "sinh", "cosh", "tanh", "Abs", "conjugate", "re", "im", "besselj", "O",
}
_CONSTANTS = {"pi", "I", "E", "oo"}


def _computed_source(node: Any, tree: Any, line: int, depth: int = 0) -> bool:
    """Whether a script's argument computes its value (diff, a product of
    matrices, an earlier result, a function of the script …) rather than
    writing it down from symbols, constants and elementary functions.
    Names are followed to their last assignment before the call. Anything
    not recognized as written down counts as computed."""
    import ast

    if depth > 12:
        return True
    rec = lambda n: _computed_source(n, tree, line, depth + 1)  # noqa: E731
    if isinstance(node, ast.Constant):
        return False
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.MatMult):
            return True
        return rec(node.left) or rec(node.right)
    if isinstance(node, ast.UnaryOp):
        return rec(node.operand)
    if isinstance(node, (ast.Tuple, ast.List)):
        return any(rec(e) for e in node.elts)
    if isinstance(node, ast.Attribute):
        return node.attr not in _CONSTANTS
    if isinstance(node, ast.Call):
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
        if name in _TYPING_CALLS:
            return any(rec(a) for a in node.args) or any(rec(k.value) for k in node.keywords)
        if isinstance(f, ast.Name):
            value = _last_assignment(tree, f.id, line)
            if (isinstance(value, ast.Call) and isinstance(value.func, (ast.Name, ast.Attribute))
                    and getattr(value.func, "attr", getattr(value.func, "id", None)) in ("function", "Function")):
                return any(rec(a) for a in node.args)  # a declared function, applied
        return True
    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return False
        value = _last_assignment(tree, node.id, line)
        return True if value is None else rec(value)
    return True


def _last_assignment(tree: Any, name: str, line: int):
    """The value last assigned to a plain name before `line`, or None."""
    import ast

    best = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and node.lineno < line:
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name and (best is None or node.lineno > best.lineno):
                    best = node
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign, ast.For, ast.With)) and node.lineno < line:
            targets = [getattr(node, "target", None)] + [getattr(i, "optional_vars", None) for i in getattr(node, "items", [])]
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                return None  # assigned in a way that is not one expression
    return best.value if best is not None else None


def _computed_sides(frame: Any, function: str, lhs: Any, rhs: Any) -> set[str] | None:
    """Which compared arguments the script computes; None without the source."""
    found = _call_node(frame, function)
    if found is None:
        return None
    call, tree = found
    import ast

    scope = tree
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.lineno <= call.lineno <= (node.end_lineno or node.lineno)
                and (scope is tree or node.lineno > scope.lineno)):
            scope = node  # names are looked up in the innermost function around the call
    tree = scope
    args = _compared_arguments(call)
    sides = set()
    for name, node, value in zip(("lhs", "rhs"), args, (lhs, rhs)):
        if _is_matrix(value) or _computed_source(node, tree, call.lineno):
            sides.add(name)
    return sides


def _as_expr(x: Any, what: str) -> Any:
    if isinstance(x, str):
        if x.startswith("step:"):
            run = _run()
            if x not in run.results:
                raise CheckError(f"{what}: {x} has not been checked yet, so it cannot be used")
            run.fetched.add(x)
            run.fetched_recent.add(x)
            return run.results[x]
        raise CheckError(
            f"{what} is a string ({x!r}). Write expressions in SymPy; the helper parses "
            "nothing. A string is allowed only as the label of an earlier step."
        )
    if isinstance(x, (list, tuple)):
        return sp.ImmutableMatrix(x)
    if isinstance(x, sp.MatrixBase):
        return sp.ImmutableMatrix(x)
    try:
        return sp.sympify(x, strict=True)
    except sp.SympifyError:
        raise CheckError(f"{what}: {x!r} is not a SymPy expression") from None


def _is_matrix(x: Any) -> bool:
    return isinstance(x, sp.MatrixBase)


def _elements(x: Any) -> list:
    return list(x) if _is_matrix(x) else [x]


def _sub(a: Any, b: Any) -> Any:
    if _is_matrix(a) or _is_matrix(b):
        if not (_is_matrix(a) and _is_matrix(b)) or a.shape != b.shape:
            raise CheckError("a matrix is compared with something of another shape")
        return sp.ImmutableMatrix(a - b)
    return a - b


def _doit(x: Any) -> Any:
    try:
        return x.doit() if hasattr(x, "doit") else x
    except Exception:  # noqa: BLE001
        return x


def _latex(x: Any) -> str:
    """LaTeX in the symbols' declared LaTeX, so it reads beside the .tex."""
    names = {}
    if _RUN is not None:
        names = {e.obj: e.latex for e in _RUN.table.values() if e.kind in ("scalar", "operator")}
    try:
        return sp.latex(x, symbol_names=names)
    except Exception:  # noqa: BLE001
        return sp.sstr(x)


def _is_zero(x: Any) -> bool:
    if _is_matrix(x):
        return all(_is_zero(e) for e in x)
    return x == 0 or getattr(x, "is_zero", None) is True


# --- the symbolic cascade ------------------------------------------------------------

_CASCADE: list[tuple[str, Callable[[Any], Any]]] = [
    ("direct comparison", lambda e: e),
    ("expand", sp.expand),
    ("cancel", sp.cancel),
    ("together", lambda e: sp.cancel(sp.together(e))),
    ("powsimp", lambda e: sp.powsimp(sp.expand(e))),
    ("trigsimp", sp.trigsimp),
    ("expand_complex", lambda e: sp.simplify(sp.expand_complex(e))),
    ("simplify", sp.simplify),
]


# Rewrites that respect the order of non-commuting factors. expand_complex
# and simplify do not: they "prove" (A + B)**2 = A**2 + 2*A*B + B**2.
_NONCOMMUTATIVE_SAFE = {"direct comparison", "expand"}


def _commutative(diff: Any) -> bool:
    return all(getattr(x, "is_commutative", True) is not False for x in _elements(diff)) and not any(
        s.is_commutative is False for s in _free_symbols(diff)
    )


def _cascade(diff: Any, timeout: float) -> str | None:
    """The first method that reduces diff to exactly zero, or None. Reaching
    zero proves the identity; not reaching it proves nothing."""
    commutative = _commutative(diff)
    for name, fn in _CASCADE:
        if not commutative and name not in _NONCOMMUTATIVE_SAFE:
            continue
        def attempt(fn=fn):
            if _is_matrix(diff):
                return all(_is_zero(fn(e)) for e in diff)
            return _is_zero(fn(diff))

        if _timed(attempt, timeout):
            return name
    return None


def _strip(symbols: Iterable, keep: set = frozenset()) -> dict:
    """Replacements that drop the declared assumptions of these symbols."""
    out = {}
    for s in symbols:
        if s in keep or not isinstance(s, sp.Symbol) or not s.is_commutative:
            continue
        out[s] = sp.Symbol(s.name)
    return out


def _residual(diff: Any, timeout: float) -> Any:
    """The shortest form of a nonzero difference that a few rewrites find."""
    best = diff
    for _, fn in _CASCADE[1:]:
        r = _timed(lambda fn=fn: diff.applyfunc(fn) if _is_matrix(diff) else fn(diff), timeout / 2)
        if r is not None and sp.count_ops(r) < sp.count_ops(best):
            best = r
    return best


# --- numerics -------------------------------------------------------------------------


def _magnitude(v: Any) -> float:
    try:
        return float(abs(sp.N(v, 15)))
    except (TypeError, ValueError):
        return math.inf


def _numeric_value(e: Any, point: dict, dps: int) -> Any:
    v = sp.N(e.xreplace(point), dps)
    if v.has(sp.nan, sp.zoo, sp.oo, -sp.oo) or v.free_symbols:
        return None
    if not v.is_number:
        return None
    return v


def _rel(diff_v: Any, scale_vs: list) -> float:
    scale = max([1.0] + [_magnitude(s) for s in scale_vs if s is not None])
    return _magnitude(diff_v) / scale


def _numeric(run: _Run, label: str, lhs: Any, rhs: Any, what: str = "points") -> dict[str, Any] | None:
    """Evaluate lhs − rhs at random points of the declared domain, exactly
    substituted and evaluated to `dps` digits (twice that to confirm a
    disagreement). None if the expressions cannot be evaluated numerically."""
    symbols = run.free(lhs, rhs)
    operators = sorted(
        (s for s in symbols if run.entry_of(s) is not None and run.entry_of(s).kind == "operator"), key=str
    )
    if _undefined_functions(lhs, rhs) or any(
        (run.entry_of(s) is None or run.entry_of(s).kind not in ("scalar", "operator")) for s in symbols
    ):
        return None
    if operators:
        return _operator_numeric(run, label, lhs, rhs, symbols, operators, what)
    rng = run.rng(label, what)
    diff = _sub(lhs, rhs)
    tol = sp.Float(10) ** (-(run.dps - 10))
    agreed, worst, tried = 0, 0.0, 0
    while agreed < run.points and tried < 4 * run.points:
        point, _ = run.sample(symbols, rng, index=tried)
        tried += 1
        if point is None:
            return None
        vals = []
        bad_point = False
        for d, l, r in zip(_elements(diff), _elements(lhs), _elements(rhs)):
            dv = _timed(lambda d=d: _numeric_value(d, point, run.dps), run.timeout)
            if dv is None:
                bad_point = True
                break
            lv = rv = None
            if _magnitude(dv) > float(tol):  # the scale matters only for a difference that is not tiny
                lv = _timed(lambda l=l: _numeric_value(l, point, 15), run.timeout)
                rv = _timed(lambda r=r: _numeric_value(r, point, 15), run.timeout)
            vals.append((d, dv, lv, rv))
        if bad_point:
            continue
        for d, dv, lv, rv in vals:
            rel = _rel(dv, [lv, rv])
            if rel > float(tol):
                dv2 = _timed(lambda d=d: _numeric_value(d, point, 2 * run.dps), run.timeout)
                rel2 = _rel(dv2, [lv, rv]) if dv2 is not None else rel
                if rel2 > float(sp.Float(10) ** (-(2 * run.dps - 10))):
                    return {
                        "agree": False,
                        "point": {str(k): sp.sstr(v) for k, v in point.items()},
                        "value": sp.sstr(sp.N(dv2 if dv2 is not None else dv, 12)),
                        "relative": f"{rel2:.3g}",
                        "dps": run.dps,
                        "seed": run.seed,
                    }
            worst = max(worst, rel)
        agreed += 1
    if agreed < max(2, run.points // 2):
        return None
    return {
        "agree": True,
        "points": agreed,
        "dps": run.dps,
        "seed": run.seed,
        "tolerance": f"relative {sp.sstr(sp.N(tol, 3))}",
        "max_relative": f"{worst:.3g}",
    }


def _operator_numeric(run, label, lhs, rhs, symbols, operators, what) -> dict[str, Any] | None:
    """Operators replaced by random 3×3 complex rational matrices. Agreement
    means the step holds in the free algebra; disagreement means it holds at
    most given relations between the operators that the table does not
    declare (commutators), so it is never a FAIL on its own."""
    if _is_matrix(lhs) or _is_matrix(rhs):
        return None
    rng = run.rng(label, what + ":operators")
    scalars = sorted((s for s in symbols if s not in operators), key=str)
    eye = sp.eye(3)
    worst = 0.0
    for _ in range(run.points):
        point, _b = run.sample(scalars, rng)
        if point is None:
            return None
        for op in operators:
            point[op] = sp.ImmutableMatrix(3, 3, [
                sp.Rational(rng.randint(-9, 9), rng.randint(1, 4))
                + sp.I * sp.Rational(rng.randint(-9, 9), rng.randint(1, 4))
                for _ in range(9)
            ])

        def value(e):
            total = sp.zeros(3, 3)
            for term in sp.Add.make_args(sp.expand(e)):
                v = term.xreplace(point)
                total += v if _is_matrix(v) else v * eye
            return total

        try:
            d = value(lhs - rhs)
            scale = max([1.0] + [_magnitude(x) for x in list(value(lhs)) + list(value(rhs))])
        except Exception:  # noqa: BLE001
            return None
        rel = max(_magnitude(x) for x in d) / scale
        if rel > 1e-12:
            return {
                "agree": False,
                "operators": True,
                "point": {str(k): ("3×3 random matrix" if k in operators else sp.sstr(v)) for k, v in point.items()},
                "value": f"largest entry of the difference {max(_magnitude(x) for x in d):.3g}",
                "relative": f"{rel:.3g}",
                "dps": "exact",
                "seed": run.seed,
            }
        worst = max(worst, rel)
    return {
        "agree": True,
        "operators": True,
        "points": run.points,
        "dps": "exact",
        "seed": run.seed,
        "tolerance": "exact rational arithmetic, operators as random 3×3 matrices",
        "max_relative": f"{worst:.3g}",
    }


def _algebraic(e: Any) -> bool:
    if _is_matrix(e):
        return all(_algebraic(x) for x in e)
    return all(
        isinstance(a, (sp.Symbol, sp.Number)) or a in (sp.I,)
        for a in e.atoms()
    ) and not e.atoms(sp.Function) and not e.has(sp.pi, sp.E)


def _exact_finite(run: _Run, label: str, diff: Any) -> dict[str, Any] | None:
    """Exact evaluation at rational points, for algebraic expressions: each
    value is an algebraic number, and its minimal polynomial decides zero."""
    if not _algebraic(diff):
        return None
    symbols = run.free(diff)
    rng = run.rng(label, "exact")
    X = sp.Symbol("X")
    done = 0
    for k in range(run.points):
        point, _b = run.sample(symbols, rng, index=k)
        if point is None:
            return None
        for d in _elements(diff):
            v = _timed(lambda d=d: sp.minimal_polynomial(d.xreplace(point), X), run.timeout)
            if v is None:
                return None
            if v != X:
                return None
        done += 1
    return {"points": done, "seed": run.seed, "method": "exact algebraic evaluation (minimal polynomial)"}


# --- mutants ------------------------------------------------------------------------


def _expr_mutants(run: _Run, e: Any, small: Any = None) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = [("×2", 2 * e)]
    terms = sp.Add.make_args(e)
    if len(terms) > 1:
        for k, t in enumerate(terms[:3]):
            out.append((f"sign of term {sp.sstr(t)}", e - 2 * t))
    else:
        out.append(("sign", -e))
    if e.has(sp.I):
        out.append(("i→−i", e.xreplace({sp.I: -sp.I})))
    pows = []
    for p in sp.preorder_traversal(e):
        if p.is_Pow and p.exp.is_Rational and p not in pows and p.base.free_symbols:
            pows.append(p)
    for p in pows[:3]:
        out.append((f"power +1 on {sp.sstr(p)}", e.xreplace({p: sp.Pow(p.base, p.exp + 1)})))
        out.append((f"power −1 on {sp.sstr(p)}", e.xreplace({p: sp.Pow(p.base, p.exp - 1)})))
    dimensional = [
        s for s in sorted(_free_symbols(e), key=str)
        if run.entry_of(s) is not None and run.entry_of(s).dim
    ]
    for s in dimensional[:2]:
        out.append((f"{s}→{s}²", e.xreplace({s: s**2})))
    if len(terms) > 1:
        if small is not None:
            def order(t):
                c, p = t.as_coeff_exponent(small)
                return p if p.is_number else 0
            drop = max(terms, key=order)
        else:
            drop = e.as_ordered_terms()[-1]
        out.append((f"drop term {sp.sstr(drop)}", e - drop))
    return out


def _swap_mutants(run: _Run, e: Any) -> list[tuple[str, Any]]:
    out = []
    syms = [s for s in sorted(_free_symbols(e), key=str) if run.entry_of(s) is not None]
    for i, a in enumerate(syms):
        for b in syms[i + 1:]:
            ea, eb = run.entry_of(a), run.entry_of(b)
            if ea.kind == eb.kind == "scalar" and ea.dim is not None and ea.dim == eb.dim:
                out.append((f"swap {a}↔{b}", e.xreplace({a: b, b: a})))
    return out[:3]


def _mutants(run: _Run, target: Any, small: Any = None) -> list[tuple[str, Any]]:
    if _is_matrix(target):
        out = []
        flat = list(target)
        nonzero = [k for k, x in enumerate(flat) if x != 0][:4]
        for k in nonzero:
            for name, m in _expr_mutants(run, flat[k], small):
                if name.startswith("i→") or name.endswith("²"):
                    continue  # applied to the whole matrix below, or not at all
                new = list(flat)
                new[k] = m
                out.append((f"element {k}: {name}", sp.ImmutableMatrix(target.rows, target.cols, new)))
        if target.has(sp.I):
            out.append(("i→−i", target.xreplace({sp.I: -sp.I})))
        out += _swap_mutants(run, target)
    else:
        out = _expr_mutants(run, target, small) + _swap_mutants(run, target)
    seen = {sp.srepr(target)}
    unique = []
    for name, m in out:
        key = sp.srepr(m)
        if key in seen:
            continue
        seen.add(key)
        unique.append((name, m))
    return unique


def _equivalent(run: _Run, label: str, a: Any, b: Any) -> bool:
    num = _numeric(run, label, a, b, what="equivalence")
    if num is not None:
        return num["agree"]
    return _cascade(_sub(a, b), run.timeout / 2) is not None


def _run_mutants(
    run: _Run,
    label: str,
    baseline: str,
    targets: list[tuple[str, Any, Callable[[Any], str]]],
    small: Any = None,
) -> dict[str, Any] | None:
    """targets: (which side, expression, judge) where judge(mutated) returns
    the verdict the same check gives the mutated expression."""
    if not run.mutants_on:
        return None
    if baseline == "FAIL":
        return {"set": MUTATION_SET, "voided": "the unmutated check failed"}
    killed, survivors, equivalent = [], [], []
    count = 0
    for side, expr, judge in targets:
        for name, m in _mutants(run, expr, small):
            if count >= MAX_MUTANTS:
                break
            count += 1
            tag = f"{side}: {name}" if len(targets) > 1 else name
            verdict = judge(m)
            if verdict not in derivfmt.PASSING:
                killed.append(tag if verdict == "FAIL" else f"{tag} ({verdict})")
            elif _equivalent(run, f"{label}:{tag}", m, expr):
                equivalent.append(tag)
            else:
                survivors.append(tag)
    return {
        "set": MUTATION_SET,
        "killed": len(killed),
        "total": len(killed) + len(survivors),
        "survivors": survivors,
        "equivalent": equivalent,
    }


def _vacuous_by_mutants(m: dict[str, Any] | None) -> bool:
    return bool(m) and "voided" not in m and m["killed"] == 0


# --- writing a verdict ------------------------------------------------------------------


def _emit(run: _Run, rec: dict[str, Any]) -> dict[str, Any]:
    label = rec["label"]
    run.fetched_recent.clear()
    run.verdicts.setdefault(label, []).append(rec["verdict"])
    run.kinds.setdefault(label, rec["check"])
    for u in rec.get("uses") or []:
        run.used.add(u)
    run.uses.setdefault(label, [])
    run.uses[label] = sorted(set(run.uses[label]) | set(rec.get("uses") or []))
    head = f"{label}  {rec['verdict']}"
    detail = rec.get("method")
    if detail:
        head += f"  {detail}"
    lines = [head]
    if rec.get("reason"):
        lines.append(f"  reason: {rec['reason']}")
    if rec.get("as_written") is not None:
        lines.append(f"  as written: {rec['as_written']}")
    elif label in run.tex_steps:
        pass
    else:
        lines.append("  as written: (no such label in the .tex)")
    if rec.get("as_checked"):
        lines.append(f"  as checked: {rec['as_checked']}")
    if rec.get("free_symbols"):
        lines.append("  symbols: " + "; ".join(rec["free_symbols"]))
    a = rec.get("assumptions")
    if a:
        lines.append(f"  assumptions needed: {a['needed']}")
    if rec.get("nonzero"):
        lines.append("  treated as nonzero: " + ", ".join(rec["nonzero"]))
    od = rec.get("outside_domain")
    if od:
        lines.append(f"  outside the declared domain: {od['holds']}" + (f" at {od['point']}" if od.get("point") else ""))
    if rec.get("numeric"):
        n = rec["numeric"]
        if n.get("agree"):
            precision = "exact" if n["dps"] == "exact" else f"{n['dps']} digits"
            lines.append(
                f"  numeric: {n['points']} points, {precision}, seed {n['seed']}, "
                f"{n['tolerance']}, worst {n['max_relative']}"
            )
    if rec.get("residual") is not None:
        lines.append(f"  residual: {rec['residual']}")
        if rec.get("residual_at"):
            lines.append(f"  residual at {rec['residual_at']['point']}: {rec['residual_at']['value']}")
    for key in ("limit", "next_term", "scaling", "order"):
        if rec.get(key) is not None:
            lines.append(f"  {key.replace('_', ' ')}: {rec[key]}")
    if rec.get("dims"):
        lines.append(f"  dimensions: {rec['dims']['lhs']} on both sides")
    m = rec.get("mutants")
    if m is None and rec["check"] not in ("unchecked",):
        lines.append("  mutants: not run")
    elif m:
        if "voided" in m:
            lines.append(f"  mutants: voided ({m['voided']})")
        else:
            lines.append(f"  mutants: {m['killed']}/{m['total']} killed ({m['set']})")
            if m["survivors"]:
                lines.append("  survived, for a person to judge: " + "; ".join(m["survivors"]))
            if m["equivalent"]:
                lines.append("  equivalent (not counted): " + "; ".join(m["equivalent"]))
    for note in rec.get("notes") or []:
        lines.append(f"  note: {note}")
    for alarm in rec.get("alarms") or []:
        lines.append(f"  alarm: {alarm}")
    if rec.get("uses"):
        inferred = set(rec.get("uses_inferred") or [])
        lines.append("  uses: " + ", ".join(
            f"{u} (found in the expression)" if u in inferred else u for u in rec["uses"]))
    run.human("\n".join(lines))
    run.record({"derivcheck": "check", **rec})
    return rec


def _base(run: _Run, label: str, check: str, uses: list[str] | None) -> dict[str, Any]:
    if not isinstance(label, str) or not label.startswith("step:"):
        raise CheckError(f"label {label!r}: step labels are 'step:…', as in the .tex \\label")
    for u in uses or []:
        if u not in run.results and u not in run.verdicts:
            raise CheckError(f"{label} uses {u}, which has not been checked yet")
    return {
        "label": label,
        "check": check,
        "as_written": run.tex_steps.get(label),
        "uses": list(uses or []),
        "alarms": [],
        "notes": [],
    }


def _clear_result(r: Any) -> bool:
    """Whether an earlier result can be looked for inside another expression:
    not a matrix, not a lone symbol or number (those occur everywhere)."""
    return isinstance(r, sp.Basic) and not _is_matrix(r) and not r.is_Atom and sp.count_ops(r) >= 1


def _contains(run: _Run, operand: Any, r: Any) -> bool:
    """Whether the checked expression r occurs in operand: as a subtree, or as
    a factor or term SymPy has merged into a larger product or sum."""
    for e in _elements(operand):
        if not isinstance(e, sp.Basic):
            continue
        if e.has(r):
            return True
        if not r.free_symbols <= e.free_symbols:
            continue
        marker = sp.Dummy("used")
        if _timed(lambda e=e: e.subs(r, marker).has(marker), min(run.timeout, 2.0)):
            return True
    return False


def _link_uses(run: _Run, rec: dict[str, Any], *operands: Any) -> set[str]:
    """Which earlier results this check's operands contain. A declared use
    whose expression does not occur is flagged as possibly re-typed; an
    undeclared one that does occur is recorded, so the chain to an export is
    complete without the script declaring every link. Returns the labels found."""
    found: set[str] = set()
    for u in rec["uses"]:
        r = run.results.get(u)
        if r is None:
            continue
        if _clear_result(r):
            if any(_contains(run, op, r) for op in operands):
                found.add(u)
            elif u in run.fetched_recent:
                found.add(u)  # taken with dc.result() for this check, then transformed (diff, limit …)
            else:
                rec["alarms"].append(
                    f"uses {u}, but its checked expression does not occur in this step: "
                    f"was it re-typed? Build on dc.result({u!r})"
                )
        elif u in run.fetched:
            found.add(u)  # a symbol, a number or a matrix: cannot be looked for reliably
        else:
            rec["alarms"].append(
                f"uses {u} but never took its expression (dc.result({u!r})): was it re-typed?"
            )
    inferred = []
    for u, r in run.results.items():
        if u == rec["label"] or u in rec["uses"] or not _clear_result(r):
            continue
        if any(_contains(run, op, r) for op in operands):
            inferred.append(u)
            found.add(u)
    if inferred:
        rec["uses"] = rec["uses"] + inferred
        rec["uses_inferred"] = inferred
    return found


def _symbols_line(run: _Run, *exprs: Any) -> list[str]:
    out = []
    for s in sorted(run.free(*exprs), key=str):
        entry = run.entry_of(s)
        out.append(entry.describe() if entry else f"{s} (not declared)")
    for f in sorted(_undefined_functions(*exprs), key=str):
        entry = run.entry_of(f)
        out.append(entry.describe() if entry else f"{f} (not declared)")
    return out


def _declared(run: _Run, *exprs: Any) -> dict[str, list[str]]:
    out = {}
    for s in sorted(run.free(*exprs), key=str):
        entry = run.entry_of(s)
        if entry and entry.assumptions:
            out[str(s)] = entry.record()["assumptions"]
    return out


def _denominators(run: _Run, *exprs: Any) -> list[str]:
    found = []
    for e in exprs:
        for x in _elements(e):
            if not isinstance(x, sp.Basic):
                continue
            for p in sp.preorder_traversal(x):
                if p.is_Pow and p.exp.is_number and p.exp.is_negative and p.base.free_symbols:
                    base = p.base
                    if base.is_zero is False:
                        continue
                    text = sp.sstr(base)
                    if text not in found:
                        found.append(text)
    return found


def _branch_notes(*exprs: Any) -> list[str]:
    notes = []
    for e in exprs:
        for x in _elements(e):
            if not isinstance(x, sp.Basic):
                continue
            for p in sp.preorder_traversal(x):
                arg = None
                if p.is_Pow and p.exp.is_Rational and not p.exp.is_integer and p.base.free_symbols:
                    if p.base.is_nonnegative is not True:
                        arg = p
                elif isinstance(p, sp.log) and p.args[0].is_positive is not True:
                    arg = p
                elif isinstance(p, (sp.atan, sp.asin, sp.acos)) and p.args[0].is_real is not True:
                    arg = p
                if arg is not None:
                    text = f"principal branch of {sp.sstr(arg)}"
                    if text not in notes:
                        notes.append(text)
    return notes[:4]


def _outside(run: _Run, label: str, diff: Any) -> dict[str, Any] | None:
    symbols = run.free(diff)
    constrained = [s for s in symbols if run.entry_of(s) and run.entry_of(s).assumptions]
    if not constrained or _undefined_functions(diff):
        return {"holds": "n/a (no declared assumptions to step outside of)"}
    point, broken = run.sample(symbols, run.rng(label, "outside"), outside=True)
    if point is None:
        return None
    plain = _strip(symbols)
    d = diff.xreplace(plain) if not _is_matrix(diff) else diff.applyfunc(lambda x: x.xreplace(plain))
    pt = {plain.get(k, k): v for k, v in point.items()}
    worst = 0.0
    for x in _elements(d):
        v = _timed(lambda x=x: _numeric_value(x, pt, run.dps), run.timeout)
        if v is None:
            return {"holds": "unknown (not finite there)", "point": {str(k): sp.sstr(v) for k, v in point.items()}}
        worst = max(worst, _magnitude(v))
    holds = worst < float(sp.Float(10) ** (-(run.dps - 10)))
    return {
        "holds": "yes" if holds else "no — the declared assumptions carry this step",
        "point": {str(k): sp.sstr(v) for k, v in point.items()},
        "broken": broken,
    }


# --- the checks ------------------------------------------------------------------------


def _judge_identity(run: _Run, label: str, lhs: Any, rhs: Any, full: bool) -> dict[str, Any]:
    """The verdict pipeline for lhs = rhs. With full=False (a mutant) it stops
    as soon as the verdict is decided."""
    diff = _sub(lhs, rhs)
    out: dict[str, Any] = {}
    num = _numeric(run, label, lhs, rhs)
    if num is not None and not num["agree"] and num.get("operators"):
        out["verdict"] = "inconclusive"
        out["method"] = (
            "with the operators as random matrices the sides differ: the step holds at "
            "most given relations between the operators (commutators) that are not declared"
        )
        out["numeric"] = num
        return out
    if num is not None and not num["agree"]:
        out["verdict"] = "FAIL"
        if full:
            res = _residual(diff, run.timeout)
            out["residual"] = sp.sstr(res)
            out["residual_latex"] = _latex(res)
            out["residual_at"] = {"point": num["point"], "value": num["value"]}
            out["numeric"] = num
            out["method"] = "numeric disagreement, confirmed at twice the precision"
        return out
    method = _cascade(diff, run.timeout if full else run.timeout / 2)
    if method is not None:
        out["verdict"] = "proved-symbolic"
        out["method"] = f"via {method}"
        out["numeric"] = num
        return out
    plain = _strip(run.free(diff))
    if plain:
        stripped = diff.xreplace(plain) if not _is_matrix(diff) else diff.applyfunc(lambda x: x.xreplace(plain))
        method = _cascade(stripped, run.timeout if full else run.timeout / 2)
        if method is not None:
            out["verdict"] = "proved-symbolic"
            out["method"] = f"via {method}, after dropping every declared assumption"
            out["numeric"] = num
            out["proved_without_assumptions"] = True
            return out
    ex = _exact_finite(run, label, diff) if full else None
    if ex is not None:
        out["verdict"] = "exact-finite"
        out["method"] = f"exact at {ex['points']} rational points"
        out["exact"] = ex
        out["numeric"] = num
        return out
    if num is not None and num["agree"]:
        out["verdict"] = "numeric-consistent"
        out["method"] = "SymPy did not reach zero; the two sides agree numerically"
        out["numeric"] = num
        return out
    out["verdict"] = "inconclusive"
    out["method"] = "SymPy did not reach zero, and the sides could not be evaluated numerically"
    if full:
        res = _residual(diff, run.timeout)
        out["residual"] = sp.sstr(res)
        out["residual_latex"] = _latex(res)
        if isinstance(res, sp.Piecewise):
            out["notes"] = ["the residual is piecewise: " + "; ".join(
                f"{sp.sstr(a.expr)} if {sp.sstr(a.cond)}" for a in res.args)]
    return out


def _needed_assumptions(run: _Run, diff: Any, proved_without: bool) -> str:
    if proved_without:
        return "none (the proof went through only after dropping every declared assumption)"
    constrained = sorted(
        (s for s in run.free(diff) if run.entry_of(s) and run.entry_of(s).assumptions), key=str
    )
    if not constrained:
        return "none declared"
    plain_all = _strip(constrained)

    def provable(repl):
        d = diff.xreplace(repl) if not _is_matrix(diff) else diff.applyfunc(lambda x: x.xreplace(repl))
        return _cascade(d, run.timeout / 4) is not None

    if provable(plain_all):
        return "none (also proved with the assumptions dropped)"
    if len(constrained) > 6:
        return "some of: " + ", ".join(run.entry_of(s).describe() for s in constrained)
    needed = [s for s in constrained if not provable(_strip([s]))]
    if not needed:
        return "jointly: " + ", ".join(run.entry_of(s).describe() for s in constrained)
    # "Needed" means: dropping that symbol's assumptions, SymPy no longer
    # reached zero within the time limit. It may be needed, or SymPy slow.
    return ", ".join(run.entry_of(s).describe() for s in needed)


def step(
    label: str, lhs: Any, rhs: Any, uses: list[str] | None = None, computed: str | None = None
) -> Any:
    """Check that lhs = rhs exactly. Returns rhs, which later steps take with
    result(label) — or by passing the label itself as lhs or rhs.
    `computed` ('lhs', 'rhs' or 'both') says which side the script computes
    rather than writes down, where the helper cannot see it."""
    run = _run()
    if computed not in (None, "lhs", "rhs", "both"):
        raise CheckError(f"{label}: computed is 'lhs', 'rhs', 'both' or None")
    uses = list(uses or [])
    for side in (lhs, rhs):
        if isinstance(side, str) and side.startswith("step:") and side not in uses:
            uses.append(side)
    rec = _base(run, label, "step", uses)
    # Comparing an expression with itself is decided from the script's source:
    # the same expression written as both arguments. Equal objects are not
    # enough. SymPy evaluates eagerly and caches, so L*P for matrices,
    # diff(u, r) and its typed result, or sqrt(s)**3 and s*sqrt(s), come out
    # as the very same object without one being a copy of the other.
    caller = sys._getframe(1)
    same_source = _same_source_arguments(caller, "step")
    raw_lhs, raw_rhs = lhs, rhs
    if same_source is None and lhs is rhs and not (isinstance(lhs, sp.Basic) and lhs.is_Atom):
        rec["alarms"].append("both sides are the same object, and the script's source could not be read to tell whether one is a copy of the other")
    same_object = bool(same_source)
    lhs = _as_expr(lhs, f"{label}: lhs")
    rhs = _as_expr(rhs, f"{label}: rhs")
    substitute = run.against_for(label)
    if substitute is not None:
        rhs = _as_expr(substitute, f"{label}: substitute")
        rec["against"] = True
        rec["notes"].append("rhs replaced by the substitute expression given with --against")
    rec["as_checked"] = f"{_latex(lhs)} = {_latex(rhs)}"
    rec["free_symbols"] = _symbols_line(run, lhs, rhs)
    built_on = _link_uses(run, rec, lhs, rhs)
    if rec["as_written"] and any(t in rec["as_written"] for t in ("\\approx", "\\simeq", "\\sim ")):
        rec["alarms"].append("the .tex states ≈ here, but it is checked as an exact identity")
    problem = run.check_symbols(lhs, rhs)
    if problem:
        rec.update(verdict="FAIL", reason=problem, mutants=None)
        run.results[label] = rhs
        _emit(run, rec)
        return rhs
    if same_object and substitute is None:
        rec.update(
            verdict="vacuous",
            reason="both sides are the same expression in the script: it is compared with itself and cannot fail",
            mutants=None,
        )
        run.results[label] = rhs
        _emit(run, rec)
        return rhs
    if lhs == rhs:
        # Identical as built is normal when a side is computed: a matrix
        # product, diff(), an earlier step's result. It is worth an alarm only
        # when both sides look written down, as a copy would be.
        sides = _computed_sides(caller, "step", raw_lhs, raw_rhs)
        is_computed = bool(
            computed or built_on or _is_matrix(lhs)
            or any(isinstance(x, str) for x in (raw_lhs, raw_rhs))
            or sides
        )
        if not is_computed:
            rec["alarms"].append(
                "the two sides are identical as built, and neither is computed: SymPy's "
                "automatic evaluation decided this step before any check ran, with any "
                "assumption it used there (positive=True turning sqrt(x**2) into x). If one "
                "side is a copy of the other, the check is vacuous; if a side is computed in "
                "a way the helper cannot see, say so with computed='lhs' (or 'rhs')"
            )
    L, R = _doit(lhs), _doit(rhs)
    try:
        rec["dims"] = run.dims_of_pair(L, R)
    except _DimError as exc:
        rec.update(verdict="FAIL", reason=f"dimensions: {exc}", mutants=None)
        run.results[label] = rhs
        _emit(run, rec)
        return rhs
    judged = _judge_identity(run, label, L, R, full=True)
    rec.update({k: v for k, v in judged.items() if k not in ("notes", "proved_without_assumptions")})
    rec["notes"] += judged.get("notes", [])
    diff = _sub(L, R)
    rec["assumption_declared"] = _declared(run, L, R)
    if rec["verdict"] in derivfmt.PASSING:
        if rec["verdict"] == "proved-symbolic":
            rec["assumptions"] = {
                "declared": rec.pop("assumption_declared"),
                "needed": _needed_assumptions(run, diff, judged.get("proved_without_assumptions", False)),
            }
        else:
            rec["assumptions"] = {"declared": rec.pop("assumption_declared"),
                                  "needed": "not determined (no symbolic proof)"}
        rec["outside_domain"] = _outside(run, label, diff)
    else:
        rec.pop("assumption_declared")
    rec["nonzero"] = _denominators(run, lhs, rhs)
    rec["notes"] += _branch_notes(L, R)

    def judge_rhs(m):
        return _judge_identity(run, label, L, _doit(m), full=False)["verdict"]

    def judge_lhs(m):
        return _judge_identity(run, label, _doit(m), R, full=False)["verdict"]

    if substitute is None:
        rec["mutants"] = _run_mutants(run, label, rec["verdict"], [("rhs", R, judge_rhs), ("lhs", L, judge_lhs)])
        if rec["verdict"] in derivfmt.PASSING and _vacuous_by_mutants(rec["mutants"]):
            rec["reason"] = "no generated mutant made this check fail: it cannot tell right from wrong"
            rec["verdict"] = "vacuous"
    else:
        rec["mutants"] = None
        rec["notes"].append("mutants not run on a substituted step")
    run.results[label] = rhs
    _emit(run, rec)
    return rhs


def _limit(expr: Any, var: Any, point: Any, dir: str | None, timeout: float) -> Any:
    kwargs = {}
    if dir is not None:
        kwargs["dir"] = dir
    elif point not in (sp.oo, -sp.oo):
        kwargs["dir"] = "+-"
    value = _timed(lambda: sp.limit(expr, var, point, **kwargs), timeout)
    if value is None or isinstance(value, sp.Limit) or value.has(sp.nan) or isinstance(value, sp.AccumBounds):
        return None
    return value


def _judge_limit(run, label, expr, var, point, dir, expected, full):
    value = _limit(_doit(expr), var, point, dir, run.timeout if full else run.timeout / 2)
    if value is None:
        return {"verdict": "inconclusive", "method": "SymPy could not take the limit"}, None
    if value in (sp.oo, -sp.oo, sp.zoo) or expected in (sp.oo, -sp.oo, sp.zoo):
        ok = value == expected
        return ({"verdict": "limit-only" if ok else "FAIL",
                 "method": "limit taken by SymPy"}
                | ({} if ok else {"residual": f"the limit is {sp.sstr(value)}, not {sp.sstr(expected)}"})), value
    judged = _judge_identity(run, label, value, expected, full=full)
    v = judged["verdict"]
    if v in derivfmt.PASSING:
        judged["verdict"] = "limit-only"
        judged["method"] = f"limit taken by SymPy, then equal to the expected value {judged.get('method', '')}".strip()
    return judged, value


def limit_case(
    label: str,
    expr: Any,
    var: Any,
    point: Any,
    expected: Any,
    dir: str | None = None,
    uses: list[str] | None = None,
) -> Any:
    """Check a special case: the limit of expr as var → point is `expected`.
    `point` may be oo or -oo; `dir` is '+' or '-' for a one-sided limit
    (two-sided when omitted). A limit check confirms one case of the step,
    never the step: its verdict is limit-only."""
    run = _run()
    uses = list(uses or [])
    if isinstance(expr, str) and expr.startswith("step:") and expr not in uses:
        uses.append(expr)
    rec = _base(run, label, "limit", uses)
    expr = _as_expr(expr, f"{label}: expr")
    expected = _as_expr(expected, f"{label}: expected")
    point = _as_expr(point, f"{label}: point")
    if dir not in (None, "+", "-"):
        raise CheckError(f"{label}: dir is '+', '-' or None (two-sided)")
    substitute = run.against_for(label)
    if substitute is not None:
        expr = _as_expr(substitute, f"{label}: substitute")
        rec["against"] = True
        rec["notes"].append("expr replaced by the substitute expression given with --against")
    arrow = f"{_latex(var)} \\to {_latex(point)}" + ({"+": "^+", "-": "^-"}[dir] if dir else "")
    rec["as_checked"] = f"\\lim_{{{arrow}}} {_latex(expr)} = {_latex(expected)}"
    rec["free_symbols"] = _symbols_line(run, expr, expected)
    _link_uses(run, rec, expr, expected)
    problem = run.check_symbols(expr, expected, var)
    if problem:
        rec.update(verdict="FAIL", reason=problem, mutants=None)
        return _emit(run, rec)
    judged, value = _judge_limit(run, label, expr, var, point, dir, expected, full=True)
    rec.update({k: v for k, v in judged.items() if k not in ("notes", "proved_without_assumptions")})
    rec["notes"] += judged.get("notes", [])
    rec["limit"] = sp.sstr(value) if value is not None else None
    rec["direction"] = dir or ("two-sided" if point not in (sp.oo, -sp.oo) else None)
    try:
        d_expr = run.dim_of(expr)
        d_exp = run.dim_of(expected)
        if d_exp and d_expr != d_exp:
            rec.update(verdict="FAIL", reason=f"dimensions: {dim_str(d_expr)} against {dim_str(d_exp)}")
    except _DimError as exc:
        rec.update(verdict="FAIL", reason=f"dimensions: {exc}")
    except _DimUnknown:
        pass

    def judge(m):
        return _judge_limit(run, label, m, var, point, dir, expected, full=False)[0]["verdict"]

    if substitute is None:
        rec["mutants"] = _run_mutants(run, label, rec["verdict"], [("expr", _doit(expr), judge)])
        if rec["verdict"] in derivfmt.PASSING and _vacuous_by_mutants(rec["mutants"]):
            rec["verdict"] = "vacuous"
            rec["reason"] = "no generated mutant of the expression changes this limit"
            if expected == 0 or expected in (sp.oo, -sp.oo):
                rec["reason"] += (
                    f"; a limit of {sp.sstr(expected)} is blind to factors — check the "
                    "leading behavior instead (divide by it and take a finite limit)"
                )
    else:
        rec["mutants"] = None
    return _emit(run, rec)


def _small_parameter(var: Any, point: Any):
    """t, and var written in t, for an expansion of var about point."""
    t = sp.Symbol("t_small", positive=True)
    if point == sp.oo:
        return t, 1 / t
    if point == -sp.oo:
        return t, -1 / t
    return t, point + t


def _order_of_O(o: Any, var: Any, point: Any) -> Any | None:
    """The power of the small parameter that an O() term stands for."""
    if o.point and o.point[0] != point:
        return None
    lead = o.expr
    c, p = lead.as_coeff_exponent(var)
    if c.has(var):
        return None
    return -p if point in (sp.oo, -sp.oo) else p


def _judge_series(run, label, exact, approx, var, order, point, eps, full):
    """Every term of exact − approx up to the stated order vanishes, and the
    error shrinks as fast as the order says."""
    out: dict[str, Any] = {"notes": []}
    t, var_of_t = _small_parameter(var, point)
    D = sp.sympify((exact - approx).xreplace({var: var_of_t}))
    n = int(sp.floor(order)) + 2
    series = None
    terms: dict[Any, Any] = {}
    for attempt in range(4):
        s = _timed(lambda n=n: sp.series(D, t, 0, n), run.timeout if full else run.timeout / 2)
        if s is None:
            break
        series = s
        terms = {}
        for term in sp.Add.make_args(sp.expand(s.removeO())):
            c, p = term.as_coeff_exponent(t)
            if c.has(t):
                series = None
                break
            terms[p] = terms.get(p, 0) + c
        if series is None:
            break
        above = [p for p, c in terms.items() if p > order and not _is_zero(sp.simplify(c))]
        if above or not full:
            break
        n += 2
    if series is None:
        out.update(verdict="inconclusive", method="SymPy could not expand exact − approx")
        return out
    numeric_only = []
    for p in sorted(terms):
        if p > order:
            continue
        c = terms[p]
        if _cascade(c, run.timeout / 2):
            continue
        num = _numeric(run, f"{label}:coeff:{p}", c, sp.Integer(0))
        if num is not None and num["agree"]:
            numeric_only.append(p)
            continue
        if num is None:
            out.update(verdict="inconclusive",
                       method=f"the coefficient of order {p} could not be decided")
            return out
        lead = (c * t**p).xreplace({t: (1 / var if point in (sp.oo, -sp.oo) else var - point)})
        out.update(
            verdict="FAIL",
            method=f"the expansions differ at order {sp.sstr(p)}, within the stated order {sp.sstr(order)}",
            residual=sp.sstr(sp.simplify(lead)),
            residual_latex=_latex(sp.simplify(lead)),
        )
        return out
    nonzero_above = sorted(p for p, c in terms.items() if p > order and not _is_zero(sp.simplify(c)))
    if nonzero_above:
        p = nonzero_above[0]
        back = (terms[p] * t**p).xreplace({t: (1 / var if point in (sp.oo, -sp.oo) else var - point)})
        out["next_term"] = sp.sstr(sp.simplify(back))
        out["next_term_latex"] = _latex(sp.simplify(back))
        out["leading_error_order"] = sp.sstr(p)
    else:
        out["next_term"] = f"none up to order {n - 1}"
    if full:
        scaling = _scaling(run, label, D, t, order, eps)
        out["scaling"] = scaling["text"]
        out["scaling_detail"] = scaling
        if scaling["status"] == "fail":
            out.update(verdict="inconclusive",
                       method="the coefficients agree, but the error does not shrink at the stated rate")
            return out
    if numeric_only:
        out.update(verdict="numeric-consistent",
                   method="coefficients of order " + ", ".join(sp.sstr(p) for p in numeric_only)
                   + " agree only numerically")
        return out
    out.update(verdict="series-verified",
               method=f"exact − approx = O({sp.sstr(var if point == 0 else t)}^{sp.sstr(order + 1)})"
               if point == 0 else f"agrees to order {sp.sstr(order)} in the small parameter")
    return out


def _scaling(run, label, D, t, order, eps):
    """|exact − approx| at ε, ε/2, ε/4: each halving should divide it by at
    least 2^(order+1). Independent of SymPy's O() arithmetic."""
    symbols = run.free(D) - {t}
    point, _ = run.sample(symbols, run.rng(label, "scaling"))
    if point is None or _undefined_functions(D):
        return {"status": "n/a", "text": "not run (the expression cannot be evaluated numerically)"}
    eps = sp.Rational(eps) if eps is not None else sp.Rational(1, 10)
    errs = []
    for k in range(3):
        pt = dict(point)
        pt[t] = eps / 2**k
        v = _timed(lambda pt=pt: _numeric_value(D, pt, 60), run.timeout)
        if v is None:
            return {"status": "n/a", "text": f"not run (not finite at ε = {sp.sstr(eps / 2**k)})"}
        errs.append(_magnitude(v) if _magnitude(v) else 0.0)
    if max(errs) < 1e-45:
        return {"status": "ok", "text": "the error vanishes at ε, ε/2, ε/4", "errors": [f"{e:.3g}" for e in errs]}
    slopes = []
    for a, b in zip(errs, errs[1:]):
        slopes.append(math.log2(a / b) if a > 0 and b > 0 else math.inf)
    need = float(order) + 1
    ok = slopes[-1] >= need - 0.3
    return {
        "status": "ok" if ok else "fail",
        "text": (
            f"|exact − approx| at ε = {sp.sstr(eps)}, ε/2, ε/4: "
            + ", ".join(f"{e:.3g}" for e in errs)
            + "; shrinks like ε^" + ", ε^".join(f"{s:.2f}" for s in slopes)
            + f" (stated: ε^{sp.sstr(order + 1)} or faster)"
        ),
        "errors": [f"{e:.3g}" for e in errs],
        "slopes": [f"{s:.3f}" for s in slopes],
    }


def series_step(
    label: str,
    exact: Any,
    approx: Any,
    var: Any,
    order: Any,
    point: Any = 0,
    eps: Any = None,
    uses: list[str] | None = None,
) -> Any:
    """Check an approximation: exact = approx + O(t^(order+1)), where t is
    var − point (or 1/var, for point oo). `approx` is written without O(),
    or with an O() term of exactly order+1. Never reported as an identity:
    its verdict is series-verified, with the first neglected term printed.
    `eps` is the value of t at which the error scaling is sampled (1/10)."""
    run = _run()
    uses = list(uses or [])
    for side in (exact, approx):
        if isinstance(side, str) and side.startswith("step:") and side not in uses:
            uses.append(side)
    rec = _base(run, label, "series", uses)
    exact = _as_expr(exact, f"{label}: exact")
    approx = _as_expr(approx, f"{label}: approx")
    point = _as_expr(point, f"{label}: point")
    order = sp.Rational(order)
    substitute = run.against_for(label)
    if substitute is not None:
        approx = _as_expr(substitute, f"{label}: substitute")
        rec["against"] = True
        rec["notes"].append("approx replaced by the substitute expression given with --against")
    rec["order"] = sp.sstr(order)
    rec["point"] = sp.sstr(point)
    rec["free_symbols"] = _symbols_line(run, exact, approx)
    _link_uses(run, rec, exact, approx.removeO() if approx.has(sp.Order) else approx)
    small = var if point == 0 else (1 / var if point in (sp.oo, -sp.oo) else var - point)
    rec["as_checked"] = (
        f"{_latex(exact)} = {_latex(approx)}" if approx.has(sp.Order)
        else f"{_latex(exact)} = {_latex(approx)} + {_latex(sp.Order(small ** (order + 1), (var, point)))}"
    )
    if rec["as_written"] is not None and not any(
        t in rec["as_written"] for t in ("\\approx", "\\simeq", "\\sim", "O(", "\\mathcal{O}", "\\order")
    ):
        rec["alarms"].append("the .tex writes this approximation as '=' with no O() term")
    problem = run.check_symbols(exact, approx.removeO() if approx.has(sp.Order) else approx, var)
    if problem:
        rec.update(verdict="FAIL", reason=problem, mutants=None)
        run.results[label] = approx
        _emit(run, rec)
        return approx
    if approx.has(sp.Order):
        o = approx.getO() if approx.is_Add or isinstance(approx, sp.Order) else None
        p_o = _order_of_O(o, var, point) if o is not None else None
        if p_o is None:
            rec.update(verdict="FAIL", reason=f"the O() term {sp.sstr(o)} is not a power of the small parameter at {sp.sstr(point)}", mutants=None)
            run.results[label] = approx
            _emit(run, rec)
            return approx
        if p_o <= order:
            rec.update(
                verdict="vacuous",
                reason=(
                    f"the O() term {sp.sstr(o)} is at or below the stated order {sp.sstr(order)}: "
                    "SymPy absorbs every term it covers, so the claim cannot fail. "
                    "Write approx without O(), or with O() of order "
                    f"{sp.sstr(order + 1)}"
                ),
                mutants=None,
            )
            run.results[label] = approx
            _emit(run, rec)
            return approx
        if p_o != order + 1:
            rec.update(verdict="FAIL", reason=(
                f"the O() term {sp.sstr(o)} does not match the stated order {sp.sstr(order)}: "
                f"set order={sp.sstr(p_o - 1)}, or write O() of order {sp.sstr(order + 1)}"), mutants=None)
            run.results[label] = approx
            _emit(run, rec)
            return approx
        approx = approx.removeO()
    if _is_zero(exact - approx):
        rec.update(verdict="vacuous", reason="exact and approx are the same expression: nothing is approximated", mutants=None)
        run.results[label] = approx
        _emit(run, rec)
        return approx
    try:
        rec["dims"] = run.dims_of_pair(_doit(exact), _doit(approx))
    except _DimError as exc:
        rec.update(verdict="FAIL", reason=f"dimensions: {exc}", mutants=None)
        run.results[label] = approx
        _emit(run, rec)
        return approx
    judged = _judge_series(run, label, _doit(exact), _doit(approx), var, order, point, eps, full=True)
    rec["notes"] += judged.pop("notes", [])
    judged.pop("scaling_detail", None)
    rec.update(judged)
    rec["nonzero"] = _denominators(run, exact, approx)

    def judge(m):
        return _judge_series(run, label, _doit(exact), m, var, order, point, eps, full=False)["verdict"]

    if substitute is None:
        rec["mutants"] = _run_mutants(run, label, rec["verdict"], [("approx", _doit(approx), judge)], small=var)
        if rec["verdict"] in derivfmt.PASSING and _vacuous_by_mutants(rec["mutants"]):
            rec["verdict"] = "vacuous"
            rec["reason"] = "no generated mutant of approx changes the verdict"
    else:
        rec["mutants"] = None
    run.results[label] = approx
    _emit(run, rec)
    return approx


def _pint_dims(run: _Run, expr: Any, expected: dict) -> str:
    """A second opinion from pint: evaluate with unit-carrying random numbers."""
    try:
        import cmath

        import pint
    except ImportError:
        return "pint not installed"
    ureg = pint.UnitRegistry()
    base = {"length": ureg.meter, "mass": ureg.kilogram, "time": ureg.second,
            "current": ureg.ampere, "temperature": ureg.kelvin,
            "amount_of_substance": ureg.mole, "luminous_intensity": ureg.candela}
    symbols = run.free(expr)
    point, _ = run.sample(symbols, run.rng("pint", sp.srepr(expr)[:40]))
    if point is None or _undefined_functions(expr) or expr.atoms(Quantity):
        return "not run (no numeric evaluation for this expression)"
    values = []
    for s in sorted(symbols, key=str):
        entry = run.entry_of(s)
        if entry is None or entry.dim is None:
            return "not run (a symbol has no declared dimension)"
        unit = ureg.dimensionless
        for name, p in entry.dim.items():
            if name not in base:
                return f"not run (no pint unit for {name})"
            unit = unit * base[name] ** float(p)
        values.append(complex(sp.N(point[s])) * unit if not point[s].is_real else float(point[s]) * unit)

    def dimless(f):
        def g(q):
            if hasattr(q, "to"):
                q = q.to("dimensionless").magnitude
            r = f(q)
            return r.real if isinstance(r, complex) and r.imag == 0 else r
        return g

    mapping = {name: dimless(getattr(cmath, name)) for name in
               ("exp", "log", "sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh")}
    mapping["sqrt"] = lambda q: q**0.5
    mapping["Abs"] = abs
    mapping["I"] = 1j
    mapping["pi"] = math.pi
    mapping["E"] = math.e
    try:
        fn = sp.lambdify(sorted(symbols, key=str), expr, modules=[mapping, "math"])
        q = fn(*values)
    except pint.DimensionalityError as exc:
        return f"pint rejects it too ({exc})"
    except Exception as exc:  # noqa: BLE001
        return f"not run ({type(exc).__name__}: {exc})"
    want = ureg.dimensionless
    for name, p in expected.items():
        if name not in base:
            return f"not run (no pint unit for {name})"
        want = want * base[name] ** float(p)
    got = q.dimensionality if hasattr(q, "dimensionality") else ureg.dimensionless.dimensionality
    return "pint agrees" if got == want.dimensionality else f"pint disagrees: {got}"


def _judge_dims(run, expr, expected):
    try:
        got = run.dim_of(_doit(expr))
    except _DimError as exc:
        return {"verdict": "FAIL", "reason": f"dimensions: {exc}"}
    except _DimUnknown as exc:
        return {"verdict": "inconclusive", "reason": f"dimensions unknown: {exc}"}
    if got != expected:
        return {"verdict": "FAIL", "reason": f"dimension {dim_str(got)}, expected {dim_str(expected)}"}
    return {"verdict": "dims-only", "method": f"dimension {dim_str(got)}"}


def dims(label: str, expr: Any, expected: Any, uses: list[str] | None = None) -> Any:
    """Check the dimension of expr, and that every argument of exp, log, trig
    and Bessel functions in it is dimensionless. Blind to dimensionless
    factors (½, 2π, a sign): the weakest positive verdict, dims-only."""
    run = _run()
    uses = list(uses or [])
    if isinstance(expr, str) and expr.startswith("step:") and expr not in uses:
        uses.append(expr)
    rec = _base(run, label, "dims", uses)
    expr = _as_expr(expr, f"{label}: expr")
    want = parse_dim(expected)
    substitute = run.against_for(label)
    if substitute is not None:
        expr = _as_expr(substitute, f"{label}: substitute")
        rec["against"] = True
    rec["as_checked"] = f"[{_latex(expr)}] = {dim_str(want)}"
    rec["free_symbols"] = _symbols_line(run, expr)
    _link_uses(run, rec, expr)
    problem = run.check_symbols(expr)
    if problem:
        rec.update(verdict="FAIL", reason=problem, mutants=None)
        return _emit(run, rec)
    rec.update(_judge_dims(run, expr, want))
    rec["notes"].append(_pint_dims(run, _doit(expr), want))

    def judge(m):
        return _judge_dims(run, m, want)["verdict"]

    if substitute is None:
        rec["mutants"] = _run_mutants(run, label, rec["verdict"], [("expr", _doit(expr), judge)])
        if rec["verdict"] in derivfmt.PASSING and _vacuous_by_mutants(rec["mutants"]):
            rec["verdict"] = "vacuous"
            rec["reason"] = "no generated mutant changes the dimension: nothing dimensional is checked"
        if rec.get("mutants") and rec["mutants"].get("survivors"):
            rec["notes"].append("a dimension check cannot see dimensionless factors; survivors are expected")
    else:
        rec["mutants"] = None
    return _emit(run, rec)


def unchecked(label: str, reason_code: str, note: str) -> None:
    """Leave a step unchecked, and say so in the output. reason_code is one of
    definition, from-source, beyond-backend, prose, deferred."""
    run = _run()
    if reason_code not in derivfmt.UNCHECKED_REASONS:
        raise CheckError(f"reason_code {reason_code!r} is not one of {sorted(derivfmt.UNCHECKED_REASONS)}")
    if not note or not note.strip():
        raise CheckError(f"{label}: say in a sentence why it is not checked")
    rec = _base(run, label, "unchecked", [])
    rec.update(verdict="unchecked", reason_code=reason_code, reason=note.strip(), mutants=None)
    if APPROXIMATION_WORDS.search(note):
        rec["alarms"].append(
            "the note reads like an approximation: an approximation is a step to check, with "
            "series_step or limit_case against the exact quantity, when that can be written down"
        )
    _emit(run, rec)


def result(label: str) -> Any:
    """The checked expression of an earlier step, to build the next one on —
    instead of typing it again."""
    run = _run()
    if label not in run.results:
        raise CheckError(f"{label} has not been checked, so it has no result to use")
    run.fetched.add(label)
    run.fetched_recent.add(label)
    return run.results[label]


def export(name: str, expr: Any, regime: dict[str, Any] | None = None, uses: list[str] | None = None) -> dict:
    """Export a result as data a later derivation can build on.

    expr is the label of the step whose checked expression is the result
    (preferred), or an expression together with `uses`, the steps it rests
    on. regime: None for an exact result, or {"small": <expr or list>,
    "order": n, "point": 0} for an approximation. The record carries the
    weakest verdict on the path to the result. Format version 0: it may
    still change, and no claim is sealed with it."""
    run = _run()
    if not isinstance(name, str) or not name.replace("_", "").replace("-", "").isalnum():
        raise CheckError(f"export name {name!r}: letters, digits, '_' and '-'")
    if name in run.export_names:
        raise CheckError(f"{name!r} is exported twice")
    run.export_names.add(name)
    step_label = None
    uses = list(uses or [])
    if isinstance(expr, str):
        step_label = expr
        if expr not in uses:
            uses.append(expr)
        expr = result(expr)
    expr = _as_expr(expr, f"export {name}")
    for u in uses:
        if u not in run.verdicts:
            raise CheckError(f"export {name} uses {u}, which was not checked")
    path = []
    stack = list(uses)
    while stack:
        x = stack.pop()
        if x in path:
            continue
        path.append(x)
        stack.extend(run.uses.get(x, []))
    path_verdicts = {lab: derivfmt.aggregate(run.verdicts.get(lab, [])) for lab in sorted(path)}
    problem = run.check_symbols(expr)
    if problem:
        raise CheckError(f"export {name}: {problem}")
    reg = None
    if regime is not None:
        if not isinstance(regime, dict) or "small" not in regime or "order" not in regime:
            raise CheckError("regime is {'small': <expr or list of expr>, 'order': n, 'point': 0}")
        smalls = regime["small"] if isinstance(regime["small"], (list, tuple)) else [regime["small"]]
        reg = {
            "small": [sp.srepr(_as_expr(s, "regime small")) for s in smalls],
            "small_latex": [_latex(_as_expr(s, "regime small")) for s in smalls],
            "order": sp.sstr(sp.Rational(regime["order"])),
            "point": sp.sstr(_as_expr(regime.get("point", 0), "regime point")),
        }
        extra = set(regime) - {"small", "order", "point"}
        if extra:
            raise CheckError(f"regime: unknown keys {sorted(extra)} (format version 0 knows small, order, point)")
    symbols = {}
    for s in sorted(run.free(expr), key=str):
        symbols[str(s)] = run.entry_of(s).record()
    for f in sorted(_undefined_functions(expr), key=str):
        symbols[str(f)] = run.entry_of(f).record()
    record = {
        "format_version": derivfmt.FORMAT_VERSION,
        "result": name,
        "expr": sp.srepr(expr),
        "latex": _latex(expr),
        "symbols": symbols,
        "regime": reg,
        "verdict": derivfmt.weakest(list(path_verdicts.values())),
        "path": path_verdicts,
        "step": step_label,
        "backend": "sympy",
        "backend_version": sp.__version__,
        "helper": HELPER_VERSION,
    }
    run.exported.extend(uses)
    run.human(
        f"export {name}: {record['latex']}  (weakest on its path: {record['verdict']}; "
        f"format_version {derivfmt.FORMAT_VERSION}, not for a sealed claim)"
    )
    run.record({"derivcheck": "export", "record": record})
    return record


# --- the run -------------------------------------------------------------------------


def begin(
    tex: str | None = None,
    seed: int = DEFAULT_SEED,
    dps: int = DEFAULT_DPS,
    points: int = DEFAULT_POINTS,
    mutants: bool = True,
    timeout: float = DEFAULT_TIMEOUT,
    script: str | None = None,
) -> None:
    """Start a run: writes the header. `tex` is the labeled derivation,
    relative to the check script; its steps are printed as written beside
    each check."""
    global _RUN
    if _RUN is not None and not _RUN.finished:
        raise CheckError("begin() was called twice in one run")
    if script is None:
        script = os.environ.get("DERIVCHECK_SCRIPT")
        if script is None:
            main = sys.modules.get("__main__")
            script = getattr(main, "__file__", None)
    _RUN = _Run(tex, seed, dps, points, mutants, timeout, script, sys.stdout)


def symbol(
    name: str,
    latex: str | None = None,
    dim: Any = None,
    kind: str = "scalar",
    convention: str | None = None,
    shape: tuple[int, int] | None = None,
    **assumptions: bool,
) -> Any:
    """Declare a symbol once: its name, LaTeX, dimension ('length', '1',
    'length/time'), kind (scalar, operator, matrix), an optional convention
    'key@version' from the ledger's conventions.json, and its assumptions
    (positive=True, real=True, …). Every verdict prints the assumptions it
    relied on."""
    return _run().symbol(name, latex, dim, kind, convention, shape, assumptions)


def function(name: str, latex: str | None = None, dim: Any = None,
             convention: str | None = None, **assumptions: bool) -> Any:
    """Declare an unspecified function, e.g. a field u(x, y, z)."""
    return _run().symbol(name, latex, dim, "function", convention, None, assumptions)


def finish() -> None:
    """Write the summary and exit: non-zero on any FAIL or vacuous verdict."""
    code = _run().finish()
    sys.stdout.flush()
    raise SystemExit(code)
