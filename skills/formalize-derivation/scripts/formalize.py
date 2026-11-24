#!/usr/bin/env python3
"""formalize.py — run, lint and compare derivation check scripts.

From the repository root, by claim id (one command, no cd):

    formalize.py run <claim-id>                # finds the check script, writes its output
    formalize.py run <claim-id> --as-written   # the run on the derivation as found
    formalize.py export <claim-id> <result>    # the exported result, as a data file
    formalize.py lock <claim-id>               # the script's uv lockfile
    formalize.py cover <claim-id>              # the coverage check

The ledger is found as claims.py finds it (the claims skill's
berry_project.py): --root, else $BERRY_CLAIMS_DIR, else the nearest
project's claims/ walking up from here to the top of the git repository
(one project of a repository that holds several), else claims/ at the top.
The path forms still work:

    formalize.py run claims/<id>/evidence/03-code.py --out claims/<id>/evidence/04-output.txt
    formalize.py export claims/<id>/evidence/04-output.txt <result> claims/<id>/evidence/05-data.json
    formalize.py lint <script> …
    formalize.py compare old-output.txt new-output.txt

`run` runs the script with `uv run --script` when uv is installed and the
script declares its dependencies (PEP 723), so the versions are pinned by
the script; otherwise with this Python, which then needs
`python3 -m pip install sympy mpmath pint`. The helper (derivcheck) is put
on the path either way. The output is written verbatim to --out and to the
terminal.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import derivfmt  # noqa: E402
import derivlint  # noqa: E402

# The ledger lookup claims.py and the hooks use, from the claims skill beside
# this one. Without it (this skill installed alone), the old rule below.
sys.path.insert(0, str(HERE.parents[1] / "claims" / "scripts"))
try:
    import berry_project  # noqa: E402
except ImportError:  # pragma: no cover - only without the claims skill
    berry_project = None


def _env(script: Path, against: str | None, mutants: bool, runner: str) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(HERE) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["DERIVCHECK_SCRIPT"] = str(script)
    env["DERIVCHECK_RUNNER"] = runner
    if against:
        env["DERIVCHECK_AGAINST"] = str(Path(against).resolve())
    else:
        env.pop("DERIVCHECK_AGAINST", None)
    if not mutants:
        env["DERIVCHECK_MUTANTS"] = "0"
    return env


def _have_sympy() -> bool:
    probe = subprocess.run(
        [sys.executable, "-c", "import sympy, mpmath"], capture_output=True, text=True
    )
    return probe.returncode == 0


# --- claim ids ----------------------------------------------------------------

CLAIM_ID = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")


class Usage(Exception):
    """A command that cannot go ahead, said in a sentence."""


def _ledger_root(given: str | None) -> Path:
    if berry_project is not None:
        return berry_project.find_ledger(Path.cwd(), given).resolve()
    if given:
        return Path(given).resolve()
    if os.environ.get("BERRY_CLAIMS_DIR"):
        return Path(os.environ["BERRY_CLAIMS_DIR"]).resolve()
    proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    top = proc.stdout.strip() if proc.returncode == 0 else ""
    return (Path(top) if top else Path.cwd()) / "claims"


def _claim(arg: str, root: str | None) -> tuple[Path, dict] | None:
    """(claim folder, claim.json) if arg is a claim id rather than a path."""
    if Path(arg).exists() or not CLAIM_ID.match(arg):
        return None
    folder = _ledger_root(root) / arg
    if not (folder / "claim.json").is_file():
        raise Usage(f"no claim {arg} in {folder.parent} (give --root, or a path)")
    return folder, json.loads((folder / "claim.json").read_text(encoding="utf-8"))


def _imports_helper(path: Path) -> bool:
    try:
        return bool(re.search(r"^\s*(import\s+derivcheck\b|from\s+derivcheck\s+import\b)",
                              path.read_text(encoding="utf-8"), re.MULTILINE))
    except (OSError, UnicodeDecodeError):
        return False


def _claim_script(folder: Path, claim: dict) -> Path:
    """The claim's check script: the listed code item that imports the helper,
    not an as-written copy; else the one such file in evidence/."""
    listed = [folder / i["file"] for i in claim.get("evidence") or []
              if i.get("kind") == "code" and i.get("file") and not derivfmt.is_as_written(i)
              and _imports_helper(folder / i["file"])]
    if not listed:
        listed = [p for p in sorted((folder / "evidence").glob("*.py"))
                  if ".as-written." not in p.name and _imports_helper(p)]
    if len(listed) != 1:
        raise Usage(
            f"{folder.name}: {'no' if not listed else len(listed)} check scripts "
            f"({', '.join(p.name for p in listed)}): give the script's path instead"
            if listed else f"{folder.name}: no check script that imports derivcheck in evidence/"
        )
    return listed[0]


def _claim_output(folder: Path, claim: dict, script: Path) -> Path:
    """Where the run of the claim's script goes: the output item it lists for
    it, else NN-output.txt after the script's number."""
    for i in claim.get("evidence") or []:
        if i.get("kind") == "output" and i.get("file") and not derivfmt.is_as_written(i):
            path = folder / i["file"]
            if not path.is_file():
                return path
            h = derivfmt.RunOutput(path.read_text(encoding="utf-8")).header or {}
            if h.get("script") == script.name:
                return path
    out = _default_output(script)
    if out.is_file() and derivfmt.JSON_KEY not in out.read_text(encoding="utf-8"):
        raise Usage(f"{out} exists and is not a derivcheck output: give --out")
    return out


def _listed(folder: Path, claim: dict, path: Path) -> bool:
    return any((folder / (i.get("file") or "")).resolve() == path.resolve() for i in claim.get("evidence") or [])


def _next_free(folder: Path, kind: str, ext: str) -> Path:
    numbers = [int(m.group(1)) for p in (folder / "evidence").iterdir()
               if (m := re.match(r"^(\d+)-", p.name))] or [0]
    return folder / "evidence" / f"{max(numbers) + 1:02d}-{kind}{ext}"


def cmd_run(a: argparse.Namespace) -> int:
    found = _claim(a.script, a.root)
    if found is not None:
        folder, claim = found
        script = _claim_script(folder, claim)
        if a.out is None and not a.as_written and not a.against:
            # A red run is never written over the evidence: give --out for it.
            a.out = str(_claim_output(folder, claim, script))
    else:
        script = Path(a.script).resolve()
    if not script.is_file():
        print(f"formalize.py: no script {script}", file=sys.stderr)
        return 2
    source = script.read_text(encoding="utf-8")
    for v in derivlint.lint(source, str(script)):
        print(f"lint: {script.name}: {v}", file=sys.stderr)
    uv = None if a.no_uv else shutil.which("uv")
    if uv and derivlint.has_inline_metadata(source):
        command = [uv, "run", "--quiet", "--script", str(script)]
        runner = "uv"
    else:
        if not _have_sympy():
            print(
                "formalize.py: SymPy is not installed for this Python, and uv is not "
                "available" + (" (or the script declares no dependencies)" if uv else "")
                + ". Install it with:\n    python3 -m pip install sympy mpmath pint",
                file=sys.stderr,
            )
            return 2
        command = [sys.executable, str(script)]
        runner = "python"
    proc = subprocess.run(
        command,
        cwd=script.parent,
        env=_env(script, a.against, not a.no_mutants, runner),
        stdout=subprocess.PIPE,
        text=True,
    )
    output = proc.stdout
    sys.stdout.write(output)
    run = derivfmt.RunOutput(output)
    out = Path(a.out) if a.out else None
    if a.as_written:
        out = _as_written_copies(script, run, out)
    if out is not None:
        out.write_text(output, encoding="utf-8")
        if found is not None and not a.as_written and not _listed(folder, claim, out):
            print(f"\nformalize.py: wrote {out}. List it in claim.json:\n    "
                  + json.dumps({"kind": "output", "file": f"evidence/{out.name}",
                                "caption": "The check's output, verbatim."}), file=sys.stderr)
        elif out is not None:
            print(f"\nformalize.py: wrote {out}", file=sys.stderr)
    if run.summary() is None:
        print("formalize.py: the run did not reach finish(); its output is incomplete", file=sys.stderr)
        return proc.returncode or 3
    if a.as_written:
        # A FAIL here is what the run is for: it is evidence, not a failed command.
        return 0
    return proc.returncode


def _with_tag(path: Path, tag: str) -> Path:
    return path.with_name(f"{path.stem}.{tag}{path.suffix}")


def _default_output(script: Path) -> Path:
    """03-code.py -> 04-output.txt beside it; otherwise <stem>-output.txt."""
    m = re.match(r"^(\d+)-", script.name)
    if m:
        return script.with_name(f"{int(m.group(1)) + 1:0{len(m.group(1))}d}-output.txt")
    return script.with_name(f"{script.stem}-output.txt")


def _as_written_copies(script: Path, run: derivfmt.RunOutput, out: Path | None) -> Path:
    """Keep the derivation as it was found: copies of the .tex and the script
    as they are now, and the output of this run, all three for the evidence."""
    h = run.header or {}
    entries = []
    if h.get("tex"):
        tex = script.parent / h["tex"]
        tex_copy = _with_tag(tex, "as-written")
        shutil.copyfile(tex, tex_copy)
        entries.append({"kind": "derivation", "file": f"evidence/{tex_copy.name}", "format": "latex",
                        "caption": f"{derivfmt.AS_WRITTEN} the derivation as it was found, before any correction."})
    script_copy = _with_tag(script, "as-written")
    shutil.copyfile(script, script_copy)
    entries.append({"kind": "code", "file": f"evidence/{script_copy.name}", "language": "python",
                    "caption": f"{derivfmt.AS_WRITTEN} the check of the derivation as it was found."})
    out = out or _with_tag(_default_output(script), "as-written")
    entries.append({"kind": "output", "file": f"evidence/{out.name}",
                    "caption": f"{derivfmt.AS_WRITTEN} its output, verbatim."})
    failed = sorted({r.get("label") for r in run.checks() if r.get("verdict") == "FAIL"})
    print(
        "\nformalize.py: kept as written: "
        + (f"{', '.join(failed)} failed. " if failed else "no step failed. ")
        + "Add these items to claim.json, then fix the .tex and the script and run again "
        "without --as-written:",
        file=sys.stderr,
    )
    for e in entries:
        print("    " + json.dumps(e, ensure_ascii=False), file=sys.stderr)
    return out


def cmd_lint(a: argparse.Namespace) -> int:
    status = 0
    for path in a.scripts:
        p = Path(path)
        violations = derivlint.lint_file(p)
        for v in violations:
            print(f"{p}: {v}")
        if not violations:
            print(f"{p}: clean (linter {derivlint.LINT_VERSION})")
        status = status or (1 if violations else 0)
        if not derivlint.has_inline_metadata(p.read_text(encoding="utf-8")):
            print(f"{p}: note: no PEP 723 block declaring its dependencies")
    return status


def cmd_compare(a: argparse.Namespace) -> int:
    old = derivfmt.comparable(Path(a.old).read_text(encoding="utf-8"))
    new = derivfmt.comparable(Path(a.new).read_text(encoding="utf-8"))
    if old == new:
        print(f"same: {len(old)} helper records agree (run nonce, hashes and timings left out)")
        return 0
    for n, (x, y) in enumerate(zip(old, new)):
        if x != y:
            keys = sorted(k for k in set(x) | set(y) if x.get(k) != y.get(k))
            print(f"record {n} ({x.get('derivcheck')} {x.get('label', '')}) differs in: {', '.join(keys)}")
    if len(old) != len(new):
        print(f"{len(old)} records against {len(new)}")
    return 1


def cmd_export(a: argparse.Namespace) -> int:
    found = _claim(a.output, a.root)
    if found is not None:
        folder, claim = found
        output = _claim_output(folder, claim, _claim_script(folder, claim))
    else:
        output = Path(a.output)
    run = derivfmt.RunOutput(output.read_text(encoding="utf-8"))
    for p in run.problems:
        print(f"formalize.py: {output}: {p}", file=sys.stderr)
    if run.problems:
        return 1
    for rec in run.exports():
        body = rec.get("record") or {}
        if body.get("result") != a.result:
            continue
        if a.dest:
            dest = Path(a.dest)
        elif found is not None:
            dest = _existing_export(folder, claim, a.result) or _next_free(folder, "data", ".json")
        else:
            raise Usage("give the destination file, or the claim id instead of the output's path")
        dest.write_text(json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{dest}: result {a.result!r}, weakest verdict on its path {body.get('verdict')}, "
              f"format_version {body.get('format_version')}")
        if found is not None and not _listed(folder, claim, dest):
            print("List it in claim.json:\n    " + json.dumps(
                {"kind": "data", "file": f"evidence/{dest.name}", "format": "json",
                 "caption": f"Exported result {a.result} (format_version {body.get('format_version')})."}))
        return 0
    names = [(r.get("record") or {}).get("result") for r in run.exports()]
    print(f"formalize.py: no export {a.result!r} in {output} (exports: {', '.join(map(str, names)) or 'none'})",
          file=sys.stderr)
    return 1


def _existing_export(folder: Path, claim: dict, result: str) -> Path | None:
    """The data item that already holds this result, to be replaced in place."""
    for i in claim.get("evidence") or []:
        if i.get("kind") in ("data", "parameters") and i.get("file"):
            try:
                data = json.loads((folder / i["file"]).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict) and data.get("result") == result and "backend" in data:
                return folder / i["file"]
    return None


def cmd_lock(a: argparse.Namespace) -> int:
    found = _claim(a.script, a.root)
    script = _claim_script(*found) if found is not None else Path(a.script).resolve()
    uv = shutil.which("uv")
    if uv is None:
        print("formalize.py: uv is not installed; without it there is no lockfile, and the "
              "versions in the output's header are the record", file=sys.stderr)
        return 2
    proc = subprocess.run([uv, "lock", "--script", str(script)], cwd=script.parent)
    lock = script.with_name(script.name + ".lock")
    if proc.returncode == 0 and lock.is_file():
        print(f"{lock}: list it in the claim as code, language toml")
    return proc.returncode


def cmd_cover(a: argparse.Namespace) -> int:
    import derivcover

    found = _claim(a.claim, a.root)
    errors, warnings = derivcover.check_folder(found[0] if found is not None else Path(a.claim))
    for e in errors:
        print(f"ERROR   {e}")
    for w in warnings:
        print(f"warning {w}")
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="formalize.py", description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--root",
        help="the ledger folder (default: the nearest project's claims/, "
        "as claims.py finds it)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("run", help="run a claim's check script (by claim id), or a script by path")
    s.add_argument("script", help="a claim id, or the check script's path")
    s.add_argument("--out", help="write the output here, verbatim")
    s.add_argument("--against", help="a JSON file {step label: expression}: re-run those "
                   "steps against substitutes (for graders and red runs; never evidence)")
    s.add_argument("--no-uv", action="store_true", help="run with this Python even if uv is installed")
    s.add_argument("--no-mutants", action="store_true", help="skip the mutants (faster; never for evidence)")
    s.add_argument("--as-written", action="store_true",
                   help="the run on the derivation as it was found, before any fix: copies the .tex "
                   "and the script to *.as-written.* and writes the output as evidence of what failed")
    s.set_defaults(run=cmd_run)

    s = sub.add_parser("lint", help="lint check scripts")
    s.add_argument("scripts", nargs="+")
    s.set_defaults(run=cmd_lint)

    s = sub.add_parser("compare", help="do two runs' outputs agree (nonce, hashes, timings aside)?")
    s.add_argument("old")
    s.add_argument("new")
    s.set_defaults(run=cmd_compare)

    s = sub.add_parser("export", help="write an exported result from a run's output to a file")
    s.add_argument("output", help="a claim id, or the run's verbatim output")
    s.add_argument("result", help="the name given to dc.export")
    s.add_argument("dest", nargs="?", help="default for a claim id: the item that holds it, else the next NN-data.json")
    s.set_defaults(run=cmd_export)

    s = sub.add_parser("lock", help="uv lock --script: the lockfile for the evidence")
    s.add_argument("script", help="a claim id, or the check script's path")
    s.set_defaults(run=cmd_lock)

    s = sub.add_parser("cover", help="the coverage check of one claim folder (claims.py check runs it too)")
    s.add_argument("claim", help="a claim id, or claims/<id>")
    s.set_defaults(run=cmd_cover)

    a = p.parse_args(argv)
    if getattr(a, "as_written", False) and a.against:
        p.error("--as-written and --against do not go together: a red run is not evidence")
    try:
        return a.run(a)
    except Usage as exc:
        print(f"formalize.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
