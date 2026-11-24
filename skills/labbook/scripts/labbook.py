#!/usr/bin/env python3
"""The labbook: the logical steps of a research project, as a LaTeX document
built from its claim ledger, rendered to PDF after every change.

    labbook/
      labbook.tex        the steps, in the researcher's voice     committed
      voice.md           how the researcher writes                committed
      berry-labbook.sty  the look                                 committed
      claims.gen.tex     boxes, figures, tables from claims/      committed, generated
      figures/           Vega-Lite specs rendered to PDF          ignored, rebuilt
      build/, *.pdf      LaTeX output; labbook.pdf               ignored, rebuilt

The prose is written by an agent (skill labbook). Everything that states a
result — the claim boxes, the figures, the papers checked, the conventions
— is generated from claims/ here, so the labbook can never say something
the ledger does not.

Figures: a claim's figure is a Vega-Lite spec with its data inline, the
same spec the Berry Science Library draws on the web. Here it is rendered
to a vector PDF with vl-convert, with a print theme (the document's font,
white background, a fixed width), and included with \\includegraphics. One
spec, two renderings, the same numbers. vl-convert comes from
`pip install vl-convert-python`, or is fetched on demand through `uv`.

Standard library only otherwise; Python 3.9+. `labbook.py -h` for commands.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "templates"
sys.path.insert(0, str(HERE.parents[1] / "record-claim" / "scripts"))

import claims as ledger_tool  # noqa: E402  (the ledger's own reader)
import hook_event  # noqa: E402  (Claude Code and Codex events alike)
import labbook_core as core  # noqa: E402  (the generator, shared with the Library)
from labbook_core import (  # noqa: E402
    FIGURE_COLOURS,
    FIGURE_FONT,
    FIGURE_WIDTH,
    print_theme,
    tex,
)


GITIGNORE = """\
# Only the sources are committed: labbook.tex, voice.md, the .sty and the
# generated claims.gen.tex. Everything below is rebuilt by labbook.py build.
build/
figures/
*.pdf
"""

class LabbookError(Exception):
    pass


# --- where things are --------------------------------------------------------------


def project_root(start: Path) -> Path:
    top = ledger_tool.git("rev-parse", "--show-toplevel", cwd=start)
    return Path(top) if top else start


class Labbook:
    def __init__(self, root: Path):
        self.root = root
        self.dir = root / "labbook"
        self.ledger = ledger_tool.Ledger(root / "claims")

    @property
    def tex(self) -> Path:
        return self.dir / "labbook.tex"

    @property
    def gen(self) -> Path:
        return self.dir / "claims.gen.tex"

    @property
    def figures(self) -> Path:
        return self.dir / "figures"

    @property
    def build_dir(self) -> Path:
        return self.dir / "build"

    @property
    def pdf(self) -> Path:
        return self.dir / "labbook.pdf"


# --- figures --------------------------------------------------------------------------------


def font_dirs() -> list[str]:
    """Where TeX Live keeps the document's font, so figures can use it."""
    kpse = shutil.which("kpsewhich")
    if not kpse:
        return []
    try:
        out = subprocess.run(
            [kpse, "IBMPlexSans-Regular.otf", "LibertinusSerif-Regular.otf"],
            capture_output=True, text=True,
        ).stdout.split()
    except OSError:
        return []
    return [str(Path(p).parent) for p in out]


def render_with_vl_convert(spec: dict[str, Any], out: Path) -> None:
    import vl_convert as vlc  # type: ignore[import-not-found]

    for d in font_dirs():
        try:
            vlc.register_font_directory(d)
        except Exception:  # noqa: BLE001 — a missing font only changes the look
            pass
    out.write_bytes(vlc.vegalite_to_pdf(spec))


def render_figure(spec_text: str, out: Path) -> str | None:
    """Render one Vega-Lite spec to PDF. None, or why it could not be."""
    try:
        spec = print_theme(json.loads(spec_text))
    except (json.JSONDecodeError, AttributeError) as exc:
        return f"not a Vega-Lite JSON spec ({exc})"
    try:
        render_with_vl_convert(spec, out)
        return None
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001 — vl-convert's errors are its own
        return f"vl-convert could not render it: {exc}"
    uv = shutil.which("uv")
    if not uv:
        return "vl-convert is not installed: pip install vl-convert-python"
    tmp = out.with_suffix(".spec.json")
    tmp.write_text(json.dumps(spec), encoding="utf-8")
    try:
        proc = subprocess.run(
            [uv, "run", "--no-project", "--quiet", "--with", "vl-convert-python",
             "python", str(Path(__file__).resolve()), "_render", str(tmp), str(out)],
            capture_output=True,
            text=True,
            timeout=300,
        )
    finally:
        tmp.unlink(missing_ok=True)
    if proc.returncode != 0 or not out.is_file():
        return (proc.stderr.strip().splitlines() or ["vl-convert failed"])[-1]
    return None


# --- what the ledger says, as LaTeX ---------------------------------------------------------


def ledger_claim(lb: Labbook, c: dict[str, Any], figures: list[dict[str, Any]]) -> dict[str, Any]:
    """A ledger claim as labbook_core takes it."""
    cid = c["id"]
    links = [{"text": f"\\texttt{{{cid}}}", "url": f"run:../claims/{cid}/claim.json"}]
    lib = c.get("library") or {}
    if lib.get("url"):
        links.append({"text": "\\berryInLibrary", "url": lib["url"]})
    citations = []
    for cit in c.get("citations") or []:
        out = {k: cit.get(k) for k in ("relation", "local", "external", "locator")}
        if cit.get("claim_id"):
            out["external"] = cit["claim_id"]
            out["url"] = f"{ledger_tool.library_url()}/{cit['claim_id']}"
        if cit.get("review"):
            out["verdict"] = (lb.ledger.source_review(cit["review"]) or {}).get("verdict")
        citations.append(out)
    return {
        "id": cid,
        "title": c.get("title"),
        "statement": c.get("statement"),
        "holds_when": c.get("holds_when"),
        "claim_type": c.get("claim_type"),
        "status": c.get("status"),
        "seal": (c.get("seal") or {}).get("sha256", "")[:8] or None,
        "links": links,
        "conventions": c.get("conventions") or [],
        "citations": citations,
        "figures": figures,
    }


def render_claim_figures(
    lb: Labbook, c: dict[str, Any], problems: list[str], render: bool
) -> list[dict[str, Any]]:
    """Render a claim's Vega-Lite figures (cached by spec); their entries."""
    out = []
    for n, item in enumerate(c.get("evidence") or [], start=1):
        is_vl = item.get("format") == "vega-lite" or str(item.get("file", "")).endswith(".vl.json")
        if item.get("kind") != "figure" or not is_vl:
            continue
        name = core.figure_name(c["id"], n)
        target = lb.dir / name
        if render:
            try:
                spec_text = ledger_tool.evidence_text(lb.ledger, c, item)
            except OSError as exc:
                problems.append(f"{c['id']} evidence {n}: {exc}")
                spec_text = None
            if spec_text is not None:
                stamp = target.with_name(target.name + ".sha256")
                digest = hashlib.sha256(
                    (spec_text + FIGURE_FONT + str(FIGURE_COLOURS) + str(FIGURE_WIDTH)
                     + core.CORE_VERSION).encode()
                ).hexdigest()
                fresh = target.is_file() and stamp.is_file() and stamp.read_text().strip() == digest
                if not fresh:
                    why = render_figure(spec_text, target)
                    if why:
                        problems.append(f"{c['id']} evidence {n}: {why}")
                    else:
                        stamp.write_text(digest)
        out.append({"n": n, "file": name if target.is_file() else "", "caption": item.get("caption")})
    return out


def generate(lb: Labbook, *, figures: bool = True) -> list[str]:
    """Write claims.gen.tex; render figures. Returns problems worth telling."""
    ledger_claims = {k: v for k, v in lb.ledger.all().items() if not v.get("_unreadable")}
    problems: list[str] = []
    if figures:
        lb.figures.mkdir(parents=True, exist_ok=True)
    claims = [
        ledger_claim(lb, c, render_claim_figures(lb, c, problems, figures))
        for _, c in sorted(ledger_claims.items())
    ]
    reviews = [
        {
            "id": rel,
            "source": r.get("source"),
            "source_version": r.get("source_version"),
            "locator": r.get("locator"),
            "verdict": r.get("verdict"),
            "summary": r.get("summary"),
            "url": (r.get("library") or {}).get("url"),
        }
        for rel, r in lb.ledger.source_reviews().items()
    ]
    conventions = [
        {"key": key, **v}
        for key, entry in sorted(lb.ledger.conventions().items())
        for v in entry.get("versions") or []
    ]
    text = core.definitions(claims, reviews, conventions)
    if not lb.gen.is_file() or lb.gen.read_text(encoding="utf-8") != text:
        lb.gen.write_text(text, encoding="utf-8")
    return problems


# --- building ----------------------------------------------------------------------------


def latex_errors(log: Path, limit: int = 6) -> str:
    if not log.is_file():
        return "no log written"
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    picked = [ln for ln in lines if ln.startswith("!") or re.match(r"^\S+\.tex:\d+:", ln)]
    return "\n".join(picked[:limit]) or "\n".join(lines[-limit:])


def compile_pdf(lb: Labbook) -> str | None:
    """LuaLaTeX via latexmk (or twice by hand). None, or what went wrong."""
    lb.build_dir.mkdir(parents=True, exist_ok=True)
    latexmk, lualatex = shutil.which("latexmk"), shutil.which("lualatex")
    if latexmk:
        cmds = [[latexmk, "-lualatex", "-interaction=nonstopmode", "-halt-on-error",
                 "-file-line-error", f"-outdir={lb.build_dir.name}", "labbook.tex"]]
    elif lualatex:
        one = [lualatex, "-interaction=nonstopmode", "-halt-on-error",
               "-file-line-error", f"-output-directory={lb.build_dir.name}", "labbook.tex"]
        cmds = [one, one]
    else:
        return "no LuaLaTeX found: install TeX Live (or MacTeX) to build the PDF"
    for cmd in cmds:
        proc = subprocess.run(cmd, cwd=lb.dir, capture_output=True, text=True)
        if proc.returncode != 0:
            return latex_errors(lb.build_dir / "labbook.log")
    shutil.copyfile(lb.build_dir / "labbook.pdf", lb.pdf)
    return None


def build(lb: Labbook) -> list[str]:
    """Generate and compile, one build at a time. A change during a build
    marks it dirty, and the running build goes once more."""
    if not lb.tex.is_file():
        raise LabbookError(f"no {lb.tex}: run labbook.py init first")
    lb.build_dir.mkdir(parents=True, exist_ok=True)
    lock, dirty = lb.build_dir / ".lock", lb.build_dir / ".dirty"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if time.time() - lock.stat().st_mtime < 600:
            dirty.touch()
            return ["a build is running; it will include this change"]
        lock.unlink(missing_ok=True)
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    try:
        while True:
            dirty.unlink(missing_ok=True)
            problems = generate(lb)
            failed = compile_pdf(lb)
            if failed:
                problems.append("LaTeX failed:\n" + failed)
            if not dirty.exists():
                return problems
    finally:
        lock.unlink(missing_ok=True)


# --- checking ------------------------------------------------------------------------------


def uncommented(text: str) -> str:
    return "\n".join(re.sub(r"(?<!\\)%.*", "", line) for line in text.splitlines())


def check(lb: Labbook) -> tuple[list[str], list[str]]:
    """(errors, sealed claims the labbook does not show yet)."""
    if not lb.tex.is_file():
        raise LabbookError(f"no {lb.tex}: run labbook.py init first")
    body = uncommented(lb.tex.read_text(encoding="utf-8"))
    claims = lb.ledger.all()
    shown = set(re.findall(r"\\claimbox\{([^}]*)\}", body))
    errors = [f"\\claimbox{{{cid}}}: no such claim in claims/" for cid in sorted(shown - set(claims))]
    for cid in re.findall(r"\\claim(?:ref|figures?)\{([^}]*)\}", body):
        if cid not in claims:
            errors.append(f"{cid}: referenced in labbook.tex, but no such claim")
    reviews = lb.ledger.source_reviews()
    for rel in re.findall(r"\\sourcebox\{([^}]*)\}", body):
        if rel not in reviews:
            errors.append(f"\\sourcebox{{{rel}}}: no such source review")
    errors += steps_without_a_claim(body)
    missing = sorted(
        cid for cid, c in claims.items() if c.get("status") == "sealed" and cid not in shown
    )
    return errors, missing


NO_CLAIM = "shows no claim"
SECTION = re.compile(r"\\section(\*?)\{([^}]*)\}")


def steps_without_a_claim(body: str) -> list[str]:
    """A step — a numbered \\section before the appendix — is one claim: its
    \\claimbox. Starred sections (where things stand, the open points,
    notes) are not steps."""
    main = re.split(r"\\appendix\b", body, maxsplit=1)[0]
    marks = list(SECTION.finditer(main))
    found = []
    for i, m in enumerate(marks):
        if m.group(1):
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(main)
        if "\\claimbox{" not in main[m.end():end]:
            found.append(
                f"step '{m.group(2).strip()}' {NO_CLAIM}: a step is a claim, shown "
                "with \\claimbox{<id>}. Record the finding as a claim first; "
                "what is not a finding goes into where things stand, the open "
                "points, or — if the researcher asked — the notes"
            )
    return found


# --- commands -------------------------------------------------------------------------------


def cmd_init(lb: Labbook, a: argparse.Namespace) -> int:
    if lb.tex.exists():
        raise LabbookError(f"{lb.tex} exists; nothing was changed")
    lb.dir.mkdir(parents=True, exist_ok=True)
    body = (TEMPLATES / f"labbook.{a.lang}.tex").read_text(encoding="utf-8")
    # The author is who the repository says, never a name the agent guessed.
    author = a.author or ledger_tool.git("config", "user.name", cwd=lb.root) or ""
    body = body.replace("@TITLE@", tex(a.title)).replace("@AUTHOR@", tex(author))
    lb.tex.write_text(body, encoding="utf-8")
    shutil.copyfile(TEMPLATES / "berry-labbook.sty", lb.dir / "berry-labbook.sty")
    if not (lb.dir / "voice.md").exists():
        shutil.copyfile(TEMPLATES / "voice.md", lb.dir / "voice.md")
    (lb.dir / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    generate(lb, figures=False)
    for path in (lb.tex, lb.dir / "voice.md", lb.dir / "berry-labbook.sty", lb.gen):
        print(path)
    return 0


def cmd_gen(lb: Labbook, a: argparse.Namespace) -> int:
    for p in generate(lb):
        print(f"warning {p}")
    print(lb.gen)
    return 0


def cmd_build(lb: Labbook, a: argparse.Namespace) -> int:
    problems = build(lb)
    for p in problems:
        print(f"warning {p}" if not p.startswith("LaTeX failed") else p)
    if any(p.startswith("LaTeX failed") for p in problems):
        return 1
    print(lb.pdf)
    return 0


def cmd_check(lb: Labbook, a: argparse.Namespace) -> int:
    errors, missing = check(lb)
    for e in errors:
        print(f"ERROR   {e}")
    for cid in missing:
        print(f"missing {cid}: sealed, but no \\claimbox{{{cid}}} in labbook.tex")
    print(f"{len(errors)} error(s), {len(missing)} sealed claim(s) not in the labbook")
    return 1 if errors else 0


# --- the hook ------------------------------------------------------------------------------

# Bash commands that change what the labbook shows.
LEDGER_COMMAND = re.compile(r"claims\.py\b.*\b(seal|published|index|conv|source)\b")


def relevant(lb: Labbook, event: dict[str, Any]) -> bool:
    """Did this tool call change what the labbook shows? A ledger command,
    or an edit inside claims/ or labbook/ (Claude Code's Edit/Write, Codex's
    apply_patch alike — see hook_event)."""
    command = hook_event.command(event)
    if command is not None:
        return bool(LEDGER_COMMAND.search(command)) or (
            "labbook.py" in command and "build" not in command
        )
    skip = (lb.build_dir.resolve(), lb.figures.resolve())
    for file in hook_event.edited_paths(event):
        if file == lb.gen.resolve() or file.suffix == ".pdf":
            continue
        if any(s == file or s in file.parents for s in skip):
            continue
        if any(d in file.parents for d in (lb.ledger.root.resolve(), lb.dir.resolve())):
            return True
    return False


def say(text: str) -> None:
    """Context for the agent on its next turn (the hook runs async)."""
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}
    }))


def start_note(lb: Labbook) -> None:
    """No labbook yet, and a claim is sealed: the labbook starts now. Said
    when the set of sealed claims changes, so not on every edit, and not
    again for the same claims."""
    sealed = sorted(
        cid for cid, c in lb.ledger.all().items() if c.get("status") == "sealed"
    )
    if not sealed:
        return
    git_dir = ledger_tool.git("rev-parse", "--absolute-git-dir", cwd=lb.root)
    marker = Path(git_dir) / "berry-labbook-start" if git_dir else None
    if marker and marker.is_file() and marker.read_text().split() == sealed:
        return
    if marker:
        try:
            marker.write_text(" ".join(sealed))
        except OSError:
            pass
    say(
        f"[labbook] {len(sealed)} claim(s) sealed, and this project has no "
        "labbook yet. Create it now, without asking: labbook.py init "
        '--title "<the project\'s question, in a few words>" --lang <en|de: '
        "the language of their messages> (the author is git config "
        "user.name); "
        "fill labbook/voice.md from their own messages; then have a step "
        "written for each sealed claim (references/labbook-writer.md, in "
        "Claude Code: berry:labbook-writer). Tell the user in one line, with "
        "the path of the PDF, and carry on with their task."
    )


def cmd_hook(lb_unused: Any, a: argparse.Namespace) -> int:
    """PostToolUse: rebuild the PDF when the ledger or the labbook changed.
    Silent when all is well; otherwise says what failed, and which sealed
    claims still need their step — once per new set."""
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    root = project_root(Path(event.get("cwd") or os.getcwd()))
    lb = Labbook(root)
    if not relevant(lb, event):
        return 0
    if not lb.tex.is_file():
        start_note(lb)
        return 0
    try:
        problems = build(lb)
        errors, missing = check(lb)
    except LabbookError:
        return 0
    notes = []
    claimless = sorted(e for e in errors if NO_CLAIM in e)
    seen = lb.build_dir / ".claimless"
    if claimless and claimless != (seen.read_text().splitlines() if seen.is_file() else []):
        notes.append(
            "[labbook] " + "\n".join(claimless[:5])
            + "\nBerry records findings as claims; the labbook shows them. "
            "Turn the prose into claims (skill record-claim), or move it out "
            "of the steps."
        )
    seen.parent.mkdir(parents=True, exist_ok=True)
    seen.write_text("\n".join(claimless))
    failed = [p for p in problems if p.startswith("LaTeX failed")]
    if failed:
        notes.append(
            "[labbook] The labbook PDF did not build; labbook/labbook.pdf is the "
            "previous version. " + failed[0] + "\nFix labbook.tex (or report a "
            "generator problem) without interrupting the user's work."
        )
    figure_trouble = [p for p in problems if not p.startswith(("LaTeX failed", "a build"))]
    if figure_trouble:
        notes.append("[labbook] " + "; ".join(figure_trouble[:3]))
    marker = lb.build_dir / ".missing"
    before = marker.read_text().split() if marker.is_file() else []
    if missing and missing != before:
        notes.append(
            "[labbook] Sealed but not yet in the labbook: " + ", ".join(missing)
            + ". Have the step written for each in the background — a "
            "background agent following the labbook skill's "
            "references/labbook-writer.md (in Claude Code: berry:labbook-writer) "
            "— and carry on with the user's work. Where nothing runs in the "
            "background, write it after answering the user."
        )
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(" ".join(missing))
    if notes:
        say("\n".join(notes))
    return 0


def cmd_render(lb_unused: Any, a: argparse.Namespace) -> int:
    """Internal: render one spec, inside an environment that has vl-convert."""
    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    render_with_vl_convert(spec, Path(a.out))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="labbook.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--root", help="the research repository (default: the git root)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="create labbook/ with the template, voice.md and .gitignore")
    s.add_argument("--title", required=True)
    s.add_argument("--author", help="default: git config user.name")
    s.add_argument("--lang", choices=["en", "de"], default="en")
    s.set_defaults(run=cmd_init)
    s = sub.add_parser("gen", help="write claims.gen.tex and render the figures")
    s.set_defaults(run=cmd_gen)
    s = sub.add_parser("build", help="gen, then compile labbook/labbook.pdf")
    s.set_defaults(run=cmd_build)
    s = sub.add_parser("check", help="claims the labbook names that do not exist, and "
                       "sealed claims it does not show yet")
    s.set_defaults(run=cmd_check)
    s = sub.add_parser("hook", help="PostToolUse hook entry: rebuild when relevant")
    s.set_defaults(run=cmd_hook)
    s = sub.add_parser("_render")
    s.add_argument("spec")
    s.add_argument("out")
    s.set_defaults(run=cmd_render)

    a = p.parse_args(argv)
    if a.command in ("hook", "_render"):
        return a.run(None, a)
    root = Path(a.root).resolve() if a.root else project_root(Path.cwd())
    try:
        return a.run(Labbook(root), a)
    except (LabbookError, ledger_tool.LedgerError) as exc:
        print(f"labbook.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
