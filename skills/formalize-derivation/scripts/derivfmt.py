"""What the helper writes and what the coverage check reads: one format.

Standard library only, so that `claims.py check` can read a run's output
without SymPy installed.

A run of a check script prints, among whatever else the script prints:

    [dc:3f9a2c1b0d4e] step:lap  proved-symbolic  via simplify; ...    a line for people
    {"derivcheck": "check", "run": "3f9a2c1b0d4e", "seq": 3, ...}    the line the check reads

Every helper line carries the run's nonce. Every JSON line also carries
`seq`, its position, and `mac`, a hash chained over the nonce, the previous
line's mac and this line's content. That makes a hand-typed, edited,
re-ordered or copied-in verdict line visible. It is tamper-evidence, not
security: the helper is open source, so anyone determined can forge a run.
Only a re-run with a trusted copy of the helper settles that.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

FORMAT_VERSION = 0

PREFIX = "dc"
HUMAN_LINE = re.compile(r"^\[dc:([0-9a-f]{12})\] ?(.*)$")
JSON_KEY = '"derivcheck":'

# Verdicts, strongest first. `formal` is reserved for a later Lean backend.
VERDICT_RANK = {
    "formal": 7,
    "proved-symbolic": 6,
    "series-verified": 6,
    "exact-finite": 5,
    "numeric-consistent": 4,
    "limit-only": 3,
    "dims-only": 2,
    "inconclusive": 1,
    "unchecked": 0,
    "vacuous": 0,
    "FAIL": -1,
}
PASSING = {
    "formal",
    "proved-symbolic",
    "series-verified",
    "exact-finite",
    "numeric-consistent",
    "limit-only",
    "dims-only",
}
ERROR_VERDICTS = {"FAIL", "vacuous"}

# Reasons a step may be left unchecked, said out loud.
UNCHECKED_REASONS = {
    "definition": "the step defines a symbol or a quantity; there is nothing to check",
    "from-source": "taken from a cited paper or claim; its review covers it",
    "beyond-backend": "SymPy cannot check this step",
    "prose": "an argument in words, not an equation",
    "deferred": "not checked yet",
}

# Words a script must not print about itself: verdicts belong to the helper.
VERDICT_WORDS = re.compile(
    r"\b(PASS(ED)?|FAIL(ED|S)?|proved-symbolic|series-verified|numeric-consistent|"
    r"exact-finite|limit-only|dims-only|vacuous)\b"
)

# The marker of the evidence that shows a derivation as it was found, before
# it was corrected: a caption that starts with this prefix, on the copy of
# the original .tex, the script that checked it and that run's output. A
# caption, because it is published with the item; an extra key would not be.
AS_WRITTEN = "As written:"


def is_as_written(item: dict[str, Any]) -> bool:
    caption = (item.get("caption") or "").strip()
    return caption.lower().startswith(AS_WRITTEN.lower())


# Keys that differ between two runs of the same script and are not part of
# what was checked: compare runs with these left out.
VOLATILE_KEYS = {"run", "mac", "seconds", "python_executable"}


def canonical(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def mac(nonce: str, previous: str, obj: dict[str, Any]) -> str:
    body = {k: v for k, v in obj.items() if k != "mac"}
    text = f"{nonce}|{previous}|{canonical(body)}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def weakest(verdicts: list[str]) -> str:
    """The weakest verdict of a chain: a chain is as strong as its weakest step."""
    if not verdicts:
        return "unchecked"
    return min(verdicts, key=lambda v: VERDICT_RANK.get(v, -2))


def aggregate(verdicts: list[str]) -> str:
    """One label's verdict from the checks run on it: any FAIL or vacuous
    check decides it; otherwise the strongest check that ran."""
    if not verdicts:
        return "unchecked"
    for bad in ("FAIL", "vacuous"):
        if bad in verdicts:
            return bad
    return max(verdicts, key=lambda v: VERDICT_RANK.get(v, -2))


# --- the .tex side ---------------------------------------------------------------

STEP_LABEL = re.compile(r"\\label\{(step:[^}]+)\}")
_BEGIN = re.compile(r"\\begin\{([A-Za-z]+\*?)\}")
_END = re.compile(r"\\end\{([A-Za-z]+\*?)\}")
_ROW_ENVS = {"align", "align*", "eqnarray", "eqnarray*", "gather", "gather*",
             "flalign", "flalign*", "alignat", "alignat*", "multline", "multline*"}


def strip_comments(tex: str) -> str:
    """LaTeX without its % comments, keeping line breaks so positions read sensibly."""
    out = []
    for line in tex.splitlines():
        m = re.search(r"(?<!\\)%", line)
        out.append(line[: m.start()] if m else line)
    return "\n".join(out)


def tex_labels(tex: str) -> list[str]:
    """The step labels of a derivation, in order, comments ignored."""
    seen: list[str] = []
    for label in STEP_LABEL.findall(strip_comments(tex)):
        if label not in seen:
            seen.append(label)
    return seen


def _enclosing_env(text: str, pos: int) -> tuple[str, int, int] | None:
    """The innermost environment around `pos`: (name, body start, body end)."""
    stack: list[tuple[str, int]] = []
    events = sorted(
        [(m.start(), "b", m.group(1), m.end()) for m in _BEGIN.finditer(text)]
        + [(m.start(), "e", m.group(1), m.end()) for m in _END.finditer(text)]
    )
    found = None
    for start, kind, name, end in events:
        if start > pos and found is None:
            # The innermost open environment at pos; find where it closes.
            if not stack:
                return None
            found = stack[-1]
        if kind == "b":
            stack.append((name, end))
        else:
            if stack and stack[-1][0] == name:
                opened = stack.pop()
                if found is not None and opened == found:
                    return found[0], found[1], start
    return None


def tex_steps(tex: str) -> dict[str, str]:
    """label -> the LaTeX of that step as written: the equation, or the row of
    an align, that carries the label, without the label itself. Plain text,
    no parsing: it is printed beside the checked expression for a reader."""
    text = strip_comments(tex)
    steps: dict[str, str] = {}
    for m in STEP_LABEL.finditer(text):
        label = m.group(1)
        if label in steps:
            continue
        env = _enclosing_env(text, m.start())
        if env is None:
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            body = text[line_start : line_end if line_end != -1 else len(text)]
        else:
            name, a, b = env
            body = text[a:b]
            if name in _ROW_ENVS:
                rows = re.split(r"\\\\", body)
                offset = a
                for row in rows:
                    if offset <= m.start() < offset + len(row) + 2:
                        body = row
                        break
                    offset += len(row) + 2
        body = STEP_LABEL.sub("", body)
        body = re.sub(r"\\(nonumber|notag)\b", "", body)
        body = re.sub(r"\\label\{[^}]*\}", "", body)
        steps[label] = " ".join(body.split())
    return steps


# --- reading a run's output --------------------------------------------------------


class RunOutput:
    """The helper's lines in a run's output, checked for having been written
    by one run of the helper, in order and unchanged."""

    def __init__(self, text: str):
        self.text = text
        self.header: dict[str, Any] | None = None
        self.records: list[dict[str, Any]] = []
        self.problems: list[str] = []
        self._read()

    @property
    def nonce(self) -> str | None:
        return (self.header or {}).get("run")

    def checks(self) -> list[dict[str, Any]]:
        return [r for r in self.records if r.get("derivcheck") == "check"]

    def exports(self) -> list[dict[str, Any]]:
        return [r for r in self.records if r.get("derivcheck") == "export"]

    def summary(self) -> dict[str, Any] | None:
        found = [r for r in self.records if r.get("derivcheck") == "summary"]
        return found[-1] if found else None

    def _read(self) -> None:
        previous = ""
        seq = 0
        human: list[tuple[int, str, str]] = []
        for n, line in enumerate(self.text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("{") and JSON_KEY in stripped:
                try:
                    obj = json.loads(stripped)
                except json.JSONDecodeError:
                    self.problems.append(f"output line {n}: a helper line that is not valid JSON")
                    continue
                if not isinstance(obj, dict) or "derivcheck" not in obj:
                    continue
                if self.header is None:
                    if obj.get("derivcheck") != "header":
                        self.problems.append(f"output line {n}: a verdict line before the helper's header")
                        continue
                    self.header = obj
                nonce = self.header.get("run", "")
                if obj.get("run") != nonce:
                    self.problems.append(
                        f"output line {n}: a verdict line from another run "
                        f"({obj.get('run')!r}, this run is {nonce!r})"
                    )
                    continue
                if obj.get("seq") != seq:
                    self.problems.append(
                        f"output line {n}: line {obj.get('seq')!r} of the run where "
                        f"{seq} was expected: lines missing, added or re-ordered"
                    )
                if obj.get("mac") != mac(nonce, previous, obj):
                    self.problems.append(
                        f"output line {n}: this verdict line was not written by the helper "
                        "as it stands (its hash does not match)"
                    )
                previous = obj.get("mac", "")
                seq = (obj.get("seq") if isinstance(obj.get("seq"), int) else seq) + 1
                if obj is not self.header:
                    self.records.append(obj)
                continue
            m = HUMAN_LINE.match(line)
            if m:
                human.append((n, m.group(1), m.group(2)))
                continue
            if VERDICT_WORDS.search(line):
                self.problems.append(
                    f"output line {n}: a verdict the helper did not write: {line.strip()[:120]!r}"
                )
        if self.header is None:
            if human or self.text.strip():
                self.problems.append("the output has no derivcheck header: was it written by the helper?")
            return
        nonce = self.header.get("run")
        known = {(r.get("label"), r.get("verdict")) for r in self.checks()}
        for n, run_id, rest in human:
            if run_id != nonce:
                self.problems.append(f"output line {n}: a helper line from another run ({run_id})")
                continue
            parts = rest.split()
            if len(parts) >= 2 and parts[0].startswith("step:"):
                if (parts[0], parts[1]) not in known:
                    self.problems.append(
                        f"output line {n}: {parts[0]} {parts[1]} has no matching verdict line"
                    )


def comparable(text: str) -> list[dict[str, Any]]:
    """A run's helper records with what legitimately differs between runs left
    out: two faithful runs of the same script give equal lists."""
    out = RunOutput(text)
    records = ([out.header] if out.header else []) + out.records
    return [{k: v for k, v in r.items() if k not in VOLATILE_KEYS} for r in records]
