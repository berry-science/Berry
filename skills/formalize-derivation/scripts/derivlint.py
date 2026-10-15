"""The linter for check scripts: a script states expressions, the helper judges.

Standard library only (it runs inside `claims.py check`). It reads the
script's syntax tree and rejects the ways a check script can decide its own
verdict, or keep the helper from deciding it:

    prints-verdict     prints PASS/FAIL (or any helper verdict) itself
    try-around-helper  wraps a helper call in try/except (or suppress)
    assert-true        asserts a constant
    eq-compare         compares with == or != (or .equals): structural, one-sided
    no-tolerance       isclose/allclose without a stated tolerance
    numbers-first      substitutes or evaluates numbers (subs with a number,
                       evalf, N, float, lambdify) before the helper's check
    monkeypatch        assigns to the helper, reaches into its internals,
                       or replaces print / stdout
    own-exit           exits on its own (finish() sets the exit code)
    no-finish          never calls finish(), or never begins

Each rule is a heuristic over the syntax, so it can be wrong in both
directions: it is a floor under the honesty of a script, not proof of it.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

LINT_VERSION = "0.1.0"

HELPER_MODULE = "derivcheck"
HELPER_CALLS = {
    "begin", "symbol", "function", "step", "limit_case", "series_step", "dims",
    "unchecked", "export", "finish", "result",
}
CHECK_CALLS = HELPER_CALLS - {"symbol", "function", "result"}
CONVENTION_REF = re.compile(r"^[a-z0-9][a-z0-9._-]*@\d+$")
VERDICT_TEXT = re.compile(
    r"\b(pass(ed|es)?|fail(ed|s|ure)?|proved|verified|correct|ok)\b|[✓✔✗✘]|\"derivcheck\"",
    re.IGNORECASE,
)
NUMERIC_CALLS = {"evalf", "N", "n", "lambdify", "nsimplify"}
TOLERANCE_KWARGS = {"rel_tol", "abs_tol", "rtol", "atol", "tol", "tolerance"}
CLOSE_CALLS = {"isclose", "allclose", "assert_allclose", "approx", "almosteq"}


class Violation:
    def __init__(self, line: int, rule: str, message: str):
        self.line = line
        self.rule = rule
        self.message = message

    def __str__(self) -> str:
        return f"line {self.line}: [{self.rule}] {self.message}"


def _is_number(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (int, float, complex)) and not isinstance(node.value, bool)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return _is_number(node.operand)
    if isinstance(node, ast.BinOp):
        return _is_number(node.left) and _is_number(node.right)
    if isinstance(node, ast.Call):
        name = _call_name(node)
        if name in {"Rational", "Float", "Integer", "S", "sympify", "Fraction", "Decimal"}:
            return bool(node.args) and all(_is_number(a) or isinstance(a, ast.Constant) for a in node.args)
    return False


def _call_name(node: ast.Call) -> str | None:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _strings_in(node: ast.AST) -> list[str]:
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return out


class _Linter(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[Violation] = []
        self.aliases: set[str] = set()  # names bound to the helper module
        self.imported: set[str] = set()  # helper functions imported by name
        self.calls: set[str] = set()
        self.try_depth = 0

    def add(self, node: ast.AST, rule: str, message: str) -> None:
        self.violations.append(Violation(getattr(node, "lineno", 0), rule, message))

    # what the helper is called in this script ----------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            if a.name.split(".")[0] == HELPER_MODULE:
                self.aliases.add(a.asname or a.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if (node.module or "").split(".")[0] == HELPER_MODULE:
            for a in node.names:
                if a.name.startswith("_"):
                    self.add(node, "monkeypatch", f"imports the helper's internal {a.name}")
                elif a.name == "*":
                    self.imported |= HELPER_CALLS
                else:
                    self.imported.add(a.asname or a.name)
        self.generic_visit(node)

    def helper_call(self, node: ast.AST) -> str | None:
        if not isinstance(node, ast.Call):
            return None
        f = node.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in self.aliases:
            return f.attr
        if isinstance(f, ast.Name) and f.id in self.imported:
            return f.id
        return None

    # the rules ----------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        helper = self.helper_call(node)
        if helper:
            self.calls.add(helper)
            if helper.startswith("_"):
                self.add(node, "monkeypatch", f"calls the helper's internal {helper}")
        if name in {"print", "write", "writelines", "info", "warning", "error"} and not helper:
            for s in _strings_in(node):
                if VERDICT_TEXT.search(s):
                    self.add(node, "prints-verdict",
                             f"prints {s.strip()[:40]!r}: verdicts are written by the helper only")
                    break
        if name in {"exit", "_exit", "quit", "abort"}:
            self.add(node, "own-exit", f"calls {name}(): finish() sets the exit code")
        if name == "equals" and not helper:
            self.add(node, "eq-compare", ".equals() decides by itself and can return None: use dc.step")
        if name in CLOSE_CALLS:
            kws = {k.arg for k in node.keywords}
            if not kws & TOLERANCE_KWARGS:
                self.add(node, "no-tolerance", f"{name}() without a stated tolerance")
        if name in {"subs", "xreplace"} and not helper:
            values: list[ast.AST] = []
            if len(node.args) == 2:
                values.append(node.args[1])
            for a in node.args:
                if isinstance(a, ast.Dict):
                    values.extend(v for v in a.values if v is not None)
                if isinstance(a, (ast.List, ast.Tuple)):
                    for el in a.elts:
                        if isinstance(el, (ast.Tuple, ast.List)) and len(el.elts) == 2:
                            values.append(el.elts[1])
            if any(_is_number(v) for v in values):
                self.add(node, "numbers-first",
                         f".{name}() puts numbers in before the check: the helper samples "
                         "points itself; for a special point use dc.limit_case")
        if name in NUMERIC_CALLS and not helper:
            self.add(node, "numbers-first",
                     f"{name}() evaluates numerically in the script: numeric checks are the helper's")
        if name == "float" and node.args and not _is_number(node.args[0]):
            self.add(node, "numbers-first", "float() of an expression: numeric checks are the helper's")
        if name == "setattr" and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in self.aliases:
            self.add(node, "monkeypatch", "setattr on the helper")
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        for sub in node.body:
            for n in ast.walk(sub):
                if self.helper_call(n):
                    self.add(node, "try-around-helper",
                             "a helper call inside try/except: a failure must reach the output")
                    break
            else:
                continue
            break
        self.generic_visit(node)

    visit_TryStar = visit_Try

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            ctx = item.context_expr
            if isinstance(ctx, ast.Call) and _call_name(ctx) in {"suppress", "redirect_stdout", "redirect_stderr"}:
                if any(self.helper_call(n) for b in node.body for n in ast.walk(b)):
                    self.add(node, "try-around-helper" if _call_name(ctx) == "suppress" else "monkeypatch",
                             f"a helper call inside {_call_name(ctx)}()")
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        test = node.test
        if isinstance(test, ast.Constant) or (isinstance(test, ast.Compare) and all(
            isinstance(x, ast.Constant) for x in [test.left, *test.comparators]
        )):
            self.add(node, "assert-true", "asserts a constant: it cannot fail")
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        operands = [node.left, *node.comparators]
        for op, left, right in zip(node.ops, operands, operands[1:]):
            if isinstance(op, (ast.Eq, ast.NotEq)):
                harmless = any(
                    isinstance(x, ast.Constant) and (isinstance(x.value, (str, bytes, bool)) or x.value is None)
                    for x in (left, right)
                )
                if not harmless:
                    self.add(node, "eq-compare",
                             "== compares structure, not value: compare expressions with dc.step")
                    break
        self.generic_visit(node)

    def _target(self, t: ast.AST, node: ast.AST) -> None:
        if isinstance(t, ast.Attribute):
            root = t
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name) and root.id in self.aliases:
                self.add(node, "monkeypatch", f"assigns to the helper ({ast.unparse(t)})")
            if isinstance(root, ast.Name) and root.id in {"sys", "builtins"} and t.attr in {
                "stdout", "stderr", "print", "modules", "exit",
            }:
                self.add(node, "monkeypatch", f"replaces {ast.unparse(t)}")
        if isinstance(t, ast.Subscript):
            if "modules" in ast.unparse(t.value):
                self.add(node, "monkeypatch", f"replaces {ast.unparse(t)}")
        if isinstance(t, ast.Name):
            if t.id in self.imported or t.id in self.aliases:
                self.add(node, "monkeypatch", f"rebinds the helper's {t.id}")
            if t.id == "print":
                self.add(node, "monkeypatch", "rebinds print")
        if isinstance(t, (ast.Tuple, ast.List)):
            for el in t.elts:
                self._target(el, node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for t in node.targets:
            self._target(t, node)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._target(node.target, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._target(node.target, node)
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for t in node.targets:
            self._target(t, node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name in self.imported or node.name == "print":
            self.add(node, "monkeypatch", f"defines its own {node.name}")
        self.generic_visit(node)


def lint(source: str, filename: str = "<check script>") -> list[Violation]:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [Violation(exc.lineno or 0, "syntax", f"the script does not parse: {exc.msg}")]
    linter = _Linter()
    # Imports first, so that aliases are known wherever they are used.
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            linter.visit(node)
    linter.violations.clear()
    linter.visit(tree)
    if not linter.aliases and not linter.imported:
        linter.violations.append(Violation(1, "no-finish", "does not import the helper (import derivcheck as dc)"))
    else:
        if "begin" not in linter.calls:
            linter.violations.append(Violation(1, "no-finish", "never calls begin()"))
        if "finish" not in linter.calls:
            linter.violations.append(Violation(1, "no-finish", "never calls finish(): the exit code would not be set"))
    return sorted(linter.violations, key=lambda v: (v.line, v.rule))


def lint_file(path: Path) -> list[Violation]:
    return lint(path.read_text(encoding="utf-8"), str(path))


def has_inline_metadata(source: str) -> bool:
    """PEP 723: a `# /// script` block declaring the dependencies."""
    return bool(re.search(r"^# /// script\s*$", source, re.MULTILINE)) and "dependencies" in source


if __name__ == "__main__":
    status = 0
    for arg in sys.argv[1:]:
        for v in lint_file(Path(arg)):
            print(f"{arg}: {v}")
            status = 1
    sys.exit(status)
