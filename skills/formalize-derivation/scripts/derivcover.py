"""The coverage check for a claim with a derivation: what `claims.py check`
runs for formalize-derivation.

Standard library only. It reads the claim's evidence — the labeled
derivation (.tex), the check script, the script's verbatim output and the
exported results — and compares them:

- the `\\label{step:…}` labels in the .tex against the step labels in the
  **output** (never in the script: a label only in a comment checks nothing);
- every verdict line in the output against the helper's hash chain;
- the script against the linter;
- the output against the files it was made from (script and .tex hashes);
- each exported result against the export record the helper wrote.

Errors: a label in the output that is not in the .tex; a FAIL or vacuous
verdict; a verdict line the helper did not write; a linter violation; an
output from another version of the script or the .tex, or from a run with
substitutes; an export file that is not what the helper wrote; a sealed
claim with a format_version 0 export; a statement that says "proved",
"verified" or "exact" over a step weaker than numeric-consistent.
Warnings: a derivation with no check at all (strongly encouraged, not
required); a .tex label the run did not check; inconclusive and unchecked
steps; alarms; weak mutation scores; mutants not run; a result not
exported; a uv run without its lockfile.

An output captioned "As written:" is the run on the derivation as it was
found, kept as evidence of what was wrong with it: its FAILs are reported,
not errors, and it counts toward nothing the claim states. The claim
still needs an unmarked output of the corrected derivation.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

import sys  # noqa: E402

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import derivfmt  # noqa: E402
import derivlint  # noqa: E402

IMPORTS_HELPER = re.compile(r"^\s*(import\s+derivcheck\b|from\s+derivcheck\s+import\b)", re.MULTILINE)
STRONG_WORDS = re.compile(r"\b(prove[ds]?|proven|verif(y|ied|ies)|exact(ly)?|rigorous(ly)?)\b", re.IGNORECASE)


def _text(folder: Path, item: dict[str, Any]) -> str | None:
    if "content" in item:
        return item.get("content") or ""
    target = (folder / item.get("file", "")).resolve()
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None  # claims.py reports a missing or unreadable file itself


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _name(item: dict[str, Any]) -> str | None:
    return Path(item["file"]).name if item.get("file") else None


def check_claim(folder: Path, claim: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(errors, warnings) for one claim. Empty if it has no derivation."""
    errors: list[str] = []
    warnings: list[str] = []
    items = [(n, item) for n, item in enumerate(claim.get("evidence") or [], start=1)]
    derivations, scripts, outputs, exports = [], [], [], []
    for n, item in items:
        text = _text(folder, item)
        if text is None:
            continue
        kind = item.get("kind")
        if kind == "derivation":
            derivations.append((n, item, text))
        elif kind == "code" and IMPORTS_HELPER.search(text):
            scripts.append((n, item, text))
        elif kind == "output" and derivfmt.JSON_KEY in text:
            outputs.append((n, item, text))
        elif kind in ("data", "parameters") and '"format_version"' in text:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and "backend" in data and "result" in data:
                exports.append((n, item, data))
    if not derivations:
        return errors, warnings

    as_written = [d for d in derivations if derivfmt.is_as_written(d[1])]
    derivations = [d for d in derivations if not derivfmt.is_as_written(d[1])]
    if not derivations:
        errors.append(
            "every derivation item is marked as written: the claim also needs the "
            "derivation its result rests on, without the marker"
        )
        return errors, warnings

    labels: list[str] = []
    for n, item, text in derivations:
        found = derivfmt.tex_labels(text)
        if not found:
            warnings.append(
                f"evidence {n} (derivation): no \\label{{step:…}} in it, so no step can be "
                "matched to a check"
            )
        labels += [x for x in found if x not in labels]

    if not scripts:
        warnings.append(
            "the derivation has no check: a SymPy check script and its verbatim output "
            "are strongly encouraged (skill formalize-derivation)"
        )
        return errors, warnings

    for n, item, text in scripts:
        for v in derivlint.lint(text, item.get("file") or "<inline>"):
            errors.append(f"evidence {n} (check script): {v}")
        if not derivlint.has_inline_metadata(text):
            warnings.append(
                f"evidence {n} (check script): no PEP 723 block declaring its dependencies "
                "(sympy, mpmath, pint)"
            )
    all_scripts = scripts
    all_derivations = derivations + as_written
    scripts = [x for x in scripts if not derivfmt.is_as_written(x[1])] or scripts

    written_outputs = [o for o in outputs if derivfmt.is_as_written(o[1])]
    outputs = [o for o in outputs if not derivfmt.is_as_written(o[1])]
    for n, item, text in written_outputs:
        _check_as_written(n, text, all_scripts, all_derivations, errors, warnings)

    if not outputs:
        if written_outputs:
            errors.append(
                "there is an as-written run but no run of the derivation the result rests "
                "on: fix the .tex and the script, run again, and list that output without "
                "the marker"
            )
        warnings.append(
            "the check script was never run into an output item: run it with "
            "formalize.py run <claim-id> and list that file"
        )
        for label in labels:
            warnings.append(f"{label}: not checked (no output)")
        return errors, warnings

    covered: dict[str, list[str]] = {}
    records_by_label: dict[str, list[dict[str, Any]]] = {}
    exported: dict[str, dict[str, Any]] = {}
    symbols: dict[str, dict[str, Any]] = {}
    any_uv = False
    for n, item, text in outputs:
        where = f"evidence {n} (output)"
        run = derivfmt.RunOutput(text)
        for p in run.problems:
            errors.append(f"{where}: {p}")
        h = run.header or {}
        if not h:
            continue
        _check_sources(where, h, scripts, derivations, errors, warnings)
        if h.get("against"):
            errors.append(
                f"{where}: a run with substitute expressions (--against "
                f"{', '.join(h['against'])}) is a red run, not evidence"
            )
        if not h.get("mutants"):
            warnings.append(f"{where}: mutants were not run, so a check that cannot fail would not show")
        installed = HERE / "derivcheck.py"
        if installed.is_file() and h.get("helper_sha256") not in (None, _sha(installed.read_text(encoding="utf-8"))):
            warnings.append(
                f"{where}: written by helper {h.get('helper')} with another hash than the "
                "installed one: a changed helper grades its own script"
            )
        if h.get("runner") == "uv":
            any_uv = True
        summary = run.summary()
        if summary is None:
            errors.append(f"{where}: the run never reached finish(): its output is incomplete")
        else:
            for a in summary.get("alarms") or []:
                warnings.append(f"{where}: alarm: {a}")
            if summary.get("unexported"):
                warnings.append(
                    f"{where}: the result is not exported: dc.export(\"<name>\", "
                    f"\"{summary['unexported']}\") in the script, then formalize.py export"
                )
            symbols.update(summary.get("symbols") or {})
        for rec in run.checks():
            records_by_label.setdefault(rec.get("label"), []).append(rec)
            covered.setdefault(rec.get("label"), []).append(rec.get("verdict"))
        for rec in run.exports():
            body = rec.get("record") or {}
            exported[body.get("result")] = body

    for label in covered:
        if label not in labels:
            errors.append(f"{label}: checked in the output, but there is no such \\label in the derivation")
    for label in labels:
        if label not in covered:
            warnings.append(f"{label}: in the derivation, but no check of it ran")

    for label, recs in records_by_label.items():
        for rec in recs:
            v = rec.get("verdict")
            why = rec.get("reason") or rec.get("residual") or rec.get("method") or ""
            if v == "FAIL":
                errors.append(f"{label}: FAIL ({rec.get('check')}): {why}")
            elif v == "vacuous":
                errors.append(f"{label}: vacuous ({rec.get('check')}): {why}")
            elif v == "inconclusive":
                warnings.append(f"{label}: inconclusive ({rec.get('check')}): {why}")
            elif v == "unchecked" and rec.get("reason_code") != "definition":
                warnings.append(f"{label}: unchecked ({rec.get('reason_code')}): {why}")
            for a in rec.get("alarms") or []:
                warnings.append(f"{label}: alarm: {a}")
            m = rec.get("mutants")
            if isinstance(m, dict) and "voided" not in m and m.get("total") and 2 * m["killed"] < m["total"]:
                warnings.append(
                    f"{label}: a weak check, {m['killed']}/{m['total']} mutants killed "
                    f"(survivors: {'; '.join(m.get('survivors') or [])})"
                )

    _check_exports(claim, exports, exported, errors, warnings)
    _check_conventions(folder, claim, symbols, errors, warnings)
    _check_strength(claim, labels, covered, records_by_label, exported, errors)

    if any_uv and not any(
        (item.get("file") or "").endswith(".lock") for _, item in items if item.get("kind") == "code"
    ):
        warnings.append(
            "the check ran under uv but its lockfile is not in the evidence "
            "(formalize.py lock <script>, then list the .lock file as code, language toml)"
        )
    return errors, warnings


def _pair(entries, name: str | None, sha: str | None):
    """The evidence item a run was made from: by content hash, else by name."""
    for entry in entries:
        if sha is not None and _sha(entry[2]) == sha:
            return entry
    return _match(entries, name)


def _check_sources(where, h, scripts, derivations, errors, warnings) -> None:
    """The output was made from these very files: the script and the .tex."""
    script = _pair(scripts, h.get("script"), h.get("script_sha256"))
    if script is None:
        errors.append(f"{where}: written by a run of {h.get('script')!r}, which is not a check script in this claim")
    elif h.get("script_sha256") != _sha(script[2]):
        errors.append(
            f"{where}: from another version of {h.get('script')} than evidence {script[0]}: "
            "run the script again and replace the output"
        )
    if h.get("tex") is None:
        warnings.append(f"{where}: the run named no .tex (dc.begin(tex=…)), so no step was shown as written")
        return
    tex = _pair(derivations, h.get("tex"), h.get("tex_sha256"))
    if tex is None:
        errors.append(f"{where}: checked {h.get('tex')!r}, which is not a derivation in this claim")
    elif h.get("tex_sha256") != _sha(tex[2]):
        errors.append(
            f"{where}: the derivation changed after the run (evidence {tex[0]}): "
            "run the check again"
        )


def _check_as_written(n, text, scripts, derivations, errors, warnings) -> None:
    """A run of the derivation as it was found, kept as evidence of what was
    wrong with it. Its FAILs are what it is for, so they are not errors; it
    counts toward nothing the claim states."""
    where = f"evidence {n} (output, as written)"
    run = derivfmt.RunOutput(text)
    for p in run.problems:
        errors.append(f"{where}: {p}")
    h = run.header or {}
    if not h:
        return
    _check_sources(where, h, scripts, derivations, errors, warnings)
    if h.get("against"):
        errors.append(f"{where}: a run with substitute expressions is a red run, not evidence")
    if run.summary() is None:
        errors.append(f"{where}: the run never reached finish(): its output is incomplete")
    failed = sorted({r.get("label") for r in run.checks() if r.get("verdict") == "FAIL"})
    if failed:
        warnings.append(
            f"{where}: {', '.join(failed)} failed on the derivation as it was found. Kept as "
            "evidence of the error: say in the reasoning which step failed and why"
        )
    else:
        warnings.append(
            f"{where}: no step failed on the derivation as it was found. If it was changed "
            "afterward, say in the reasoning that the check did not catch what was changed"
        )


def _match(entries: list[tuple[int, dict[str, Any], Any]], name: str | None):
    if name is None:
        return None
    for entry in entries:
        if _name(entry[1]) == name:
            return entry
    if len(entries) == 1 and entries[0][1].get("file") is None:
        return entries[0]
    return None


def _check_exports(claim, exports, exported, errors, warnings) -> None:
    for n, item, data in exports:
        where = f"evidence {n} (exported result {data.get('result')!r})"
        written = exported.get(data.get("result"))
        if written is None:
            errors.append(f"{where}: no run in this claim exported it: it was not written by the helper")
        elif written != data:
            changed = sorted(k for k in set(written) | set(data) if written.get(k) != data.get(k))
            errors.append(f"{where}: differs from what the helper exported, in {', '.join(changed)}")
        if data.get("format_version") == 0 and claim.get("status") == "sealed":
            errors.append(
                f"{where}: format_version 0 may still change; a claim with a v0 export is "
                "not sealed (the format freezes at v1)"
            )
    listed = {data.get("result") for _, _, data in exports}
    for name in exported:
        if name not in listed:
            warnings.append(
                f"result {name!r} was exported by the run but is not in the evidence "
                "(formalize.py export <output> " + str(name) + " evidence/NN-data.json)"
            )


def _check_conventions(folder: Path, claim, symbols, errors, warnings) -> None:
    named = {e.get("convention") for e in symbols.values() if e.get("convention")}
    if not named:
        return
    path = folder.parent / "conventions.json"
    defined: dict[str, set[int]] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for c in data.get("conventions") or []:
                defined[c.get("key")] = {v.get("version") for v in c.get("versions") or []}
        except json.JSONDecodeError:
            return  # claims.py reports the broken file
    for ref in sorted(named):
        key, _, version = ref.partition("@")
        users = ", ".join(sorted(s for s, e in symbols.items() if e.get("convention") == ref))
        if not version.isdigit() or int(version) not in defined.get(key, set()):
            errors.append(f"symbol {users}: convention {ref} is not in conventions.json")
        elif ref not in (claim.get("conventions") or []):
            warnings.append(f"symbol {users} is written in {ref}, which the claim's conventions do not name")


def _check_strength(claim, labels, covered, records_by_label, exported, errors) -> None:
    text = " ".join(str(claim.get(k) or "") for k in ("title", "statement"))
    word = STRONG_WORDS.search(text)
    if not word:
        return
    if exported:
        path: dict[str, str] = {}
        for rec in exported.values():
            path.update(rec.get("path") or {})
    else:
        path = {lab: derivfmt.aggregate(covered.get(lab, [])) for lab in labels}

    def definition(lab: str) -> bool:
        recs = records_by_label.get(lab) or []
        return bool(recs) and all(r.get("reason_code") == "definition" for r in recs)

    weak = sorted(
        f"{lab} ({v})" for lab, v in path.items()
        if derivfmt.VERDICT_RANK.get(v, -2) < derivfmt.VERDICT_RANK["numeric-consistent"]
        and not (v == "unchecked" and definition(lab))
    )
    if weak:
        errors.append(
            f"the claim says {word.group(0)!r}, but on the way to its result "
            + ", ".join(weak)
            + " is weaker than numeric-consistent: say what was checked, not more"
        )


def check_folder(folder: Path) -> tuple[list[str], list[str]]:
    claim = json.loads((folder / "claim.json").read_text(encoding="utf-8"))
    return check_claim(folder, claim)
