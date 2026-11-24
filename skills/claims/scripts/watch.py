#!/usr/bin/env python3
"""PostToolUse hook: notice when a run may have settled something.

Runs in a research project that keeps a claim ledger, or where Berry is
enabled in the project's .claude/settings.json, or with BERRY_WATCH=1. The
project is the nearest folder up from the session's directory with a
claims/ ledger or Berry enabled, else the git root (berry_project.py): a
repository can hold several projects, and each keeps its own state. It never blocks and never
asks the researcher anything. It looks where results appear: a command
that printed numbers (not git or ls or a test suite), and a run's output
read later — `tail run.log`, the Read tool on a .log or .csv, a background
command's output fetched — because a long run goes to the background and
its results are seen only when its log is read. Then it hands the agent a
short note: decide whether this reached claim level
(references/claim-threshold.md), and if it did, write the claim and start
the independent claim-checker in the background while the work goes on.

The judgment is the agent's, because only it knows what the numbers mean;
this script only decides *when* to ask, cheaply, and not too often: at most
once per BERRY_WATCH_INTERVAL seconds (default 600) per session. Results
seen in between are kept for the next note. `watch.py remind`, on the
user's next message, brings back a note nobody acted on — no claim written
since — once.

Standard library only. Exit 0 always: a monitor that breaks the session is
worse than none.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "claims" / "scripts"))
import berry_project  # noqa: E402  (which project, which ledger)
import hook_event  # noqa: E402  (Claude Code and Codex events alike)

# The first word of commands that do not produce findings.
QUIET = {
    "git", "ls", "cat", "head", "tail", "less", "grep", "rg", "find", "cd",
    "echo", "printf", "pwd", "which", "mkdir", "rm", "mv", "cp", "touch",
    "sed", "awk", "wc", "sort", "diff", "open", "chmod", "ln", "tree", "du",
    "df", "ps", "kill", "env", "export", "source", "pip", "pip3", "brew",
    "npm", "npx", "yarn", "pnpm", "conda", "mamba", "gh", "ssh", "scp",
    "rsync", "curl", "wget", "tar", "zip", "unzip", "docker", "kubectl",
    "sleep", "date", "true", "false", "test", "clear", "history", "man",
    "code", "cursor", "latexmk", "lualatex", "pdflatex", "xelatex",
}
# Anywhere in the command: tools whose output is not a research result.
NOT_A_RUN = re.compile(
    r"(claims\.py|labbook\.py|watch\.py|pytest|unittest|ruff|mypy|pyright|"
    r"black|flake8|eslint|prettier|pip install|uv (add|sync|lock|pip)|"
    r"--help|\s-h\b|--version)"
)
# Commands that only show a file: quiet, unless the file is a run's output.
READERS = {"cat", "tail", "head", "less", "more"}
# A run's output: a log, a data table, or Claude Code's file for a command
# that ran in the background.
OUTPUT_FILE = re.compile(r"\.(?:log|out|err|txt|csv|tsv|dat)\b|/tasks/[\w.-]+\.output\b")
# Results noticed while the monitor is quiet are kept for the next note.
MAX_PENDING = 5
# A number worth noticing: a decimal or an exponent, not a line number.
RESULT_NUMBER = re.compile(r"(?<![\w.])[-+]?\d+\.\d+(?:[eE][-+]?\d+)?|\d[eE][-+]?\d+")
MIN_NUMBERS = 2


def first_word(command: str) -> str:
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    while words and ("=" in words[0] and not words[0].startswith("-")):
        words = words[1:]  # FOO=1 python run.py
    if words and words[0] in ("sudo", "time", "nohup", "caffeinate"):
        words = words[1:]
    return Path(words[0]).name if words else ""


def result_lines(text: str) -> list[str]:
    """The lines that carry results, or [] if there are too few numbers."""
    lines = [ln.strip() for ln in text.splitlines() if RESULT_NUMBER.search(ln)]
    count = sum(len(RESULT_NUMBER.findall(ln)) for ln in lines)
    return lines if count >= MIN_NUMBERS else []


def reads_output(command: str) -> bool:
    """Is this command reading a run's output file — `tail -20 run.log`,
    `cat out/fit.csv | head`? A long run goes to the background and writes
    a log; its results are seen when the log is read, not when it starts."""
    last = re.split(r"&&|;|\|\|", command)[-1].strip()
    return first_word(last) in READERS and bool(OUTPUT_FILE.search(last))


def looks_like_a_run(command: str, stdout: str) -> list[str]:
    """The lines of output that carry results, or [] if it was not a run."""
    if not stdout.strip() or NOT_A_RUN.search(command):
        return []
    # Several commands chained: judge by the last one, which printed last.
    last = re.split(r"&&|;|\|\|", command)[-1].strip()
    quiet = first_word(last) in QUIET or first_word(command) in QUIET and last == command
    if quiet and not reads_output(command):
        return []
    return result_lines(stdout)


def drafts(ledger: Path) -> list[str]:
    found = []
    for file in sorted(ledger.glob("*/claim.json")):
        try:
            if json.loads(file.read_text(encoding="utf-8")).get("status") == "draft":
                found.append(file.parent.name)
        except (OSError, json.JSONDecodeError):
            continue
    return found


def state_file(project: berry_project.Project) -> Path:
    """berry-watch.json in the git directory, one per project: two projects
    in one repository share neither the rate limit nor what was noticed."""
    return project.state_file("berry-watch.json")


def load_state(project: berry_project.Project) -> dict[str, Any]:
    try:
        state = json.loads(state_file(project).read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return state if isinstance(state, dict) else {}


def save_state(project: berry_project.Project, state: dict[str, Any]) -> None:
    now = time.time()
    # Forget sessions older than a day, so the file does not grow forever.
    state = {k: v for k, v in state.items() if now - float(session(state, k)["touched"]) < 86400}
    try:
        state_file(project).write_text(json.dumps(state))
    except OSError:
        pass


def session(state: dict[str, Any], key: str) -> dict[str, Any]:
    """One session's record: when it was last noted, what was noticed while
    it was quiet, and what the last note was about."""
    entry = state.get(key)
    if not isinstance(entry, dict):  # an older file: only the time
        entry = {"last": float(entry or 0)}
    entry.setdefault("last", 0.0)
    entry.setdefault("pending", [])
    entry.setdefault("touched", entry["last"])
    state[key] = entry
    return entry


def observed(event: dict[str, Any]) -> dict[str, Any] | None:
    """What this tool call showed of a result: {"what", "lines"}, or None.
    A command that ran and printed numbers; a run's output file read; the
    output of a background command fetched."""
    command = hook_event.command(event)
    if command is not None:
        if hook_event.interrupted(event):
            return None
        lines = looks_like_a_run(command, hook_event.output(event))
        return {"what": f"$ {command[:200]}", "lines": lines[-4:]} if lines else None
    read = hook_event.read_result(event)
    if read is None:
        return None
    what, text = read
    if hook_event.tool(event) in hook_event.READ_TOOLS and not OUTPUT_FILE.search(what):
        return None
    lines = result_lines(text)
    return {"what": f"read {what[:200]}", "lines": lines[-4:]} if lines else None


def note(items: list[dict[str, Any]], waiting: list[str], has_ledger: bool) -> str:
    shown = "\n".join(
        f"  {item['what']}\n" + "\n".join(f"    {ln[:160]}" for ln in item["lines"])
        for item in items
    )
    text = (
        "[claims] Results were printed or read:\n"
        f"{shown}\n"
        "Is this a claim (skill claims, claim-threshold.md)? If not, say "
        "nothing. If it is, write claims/<id>/claim.md yourself (claims.py "
        "new; evidence as paths to the output on disk) and start the claim-checker in "
        "the background (Claude Code: berry:claim-checker). Never interrupt "
        "the user: carry on with their task."
    )
    if not has_ledger:
        text += (
            "\nBerry is enabled for this project but it has no claim ledger "
            "yet: if this is a finding, recording it starts the ledger "
            "(claims.py new creates claims/), with the one setup message of "
            "the first claim (skill claims)."
        )
    if waiting:
        text += (
            f"\nDrafts not yet sealed ({len(waiting)}): "
            + ", ".join(waiting[:6])
            + ". Nothing builds on a draft until the claim-checker has sealed it."
        )
    return text


def reminder(items: list[dict[str, Any]]) -> str:
    shown = "\n".join(f"  {item['what']}" for item in items)
    return (
        "[claims] Results noticed earlier in this session, and no claim "
        f"was written since:\n{shown}\n"
        "Decide now, beside the user's request, whether each is a claim "
        "(claim-threshold.md); if one is, write its claim.md and start the "
        "claim-checker in the background. If you already judged them not to "
        "be claims, ignore this note. It is not repeated."
    )


# Drafts older than this are brought up once per session.
DRAFT_AGE = float(os.environ.get("BERRY_DRAFT_AGE", "3600"))


def waiting_long(ledger: Path) -> list[str]:
    """Drafts whose claim.json has not changed for DRAFT_AGE seconds."""
    now = time.time()
    old = []
    for cid in drafts(ledger) if ledger.is_dir() else []:
        try:
            if now - (ledger / cid / "claim.json").stat().st_mtime >= DRAFT_AGE:
                old.append(cid)
        except OSError:
            continue
    return old


def drafts_note(old: list[str]) -> str:
    return (
        f"[claims] {len(old)} draft(s) still unsealed: "
        + ", ".join(old[:8]) + ". If the claim-checker has not run on one, "
        "start it. Held ones (claims.py pending shows their open issues) go "
        "to the user at a natural pause, not in the middle of their task."
    )


def watching(project: berry_project.Project) -> bool:
    return (
        project.has_ledger
        or os.environ.get("BERRY_WATCH") == "1"
        or project.enabled
    )


def drafted_since(ledger: Path, when: float) -> bool:
    try:
        return any(f.stat().st_mtime >= when for f in ledger.glob("*/claim.json"))
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    mode = (argv if argv is not None else sys.argv[1:])[:1]
    try:
        event: dict[str, Any] = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    project = berry_project.find_project(event.get("cwd") or None)
    if not watching(project):
        return 0
    ledger = project.ledger
    key = str(event.get("session_id") or "session")
    state = load_state(project)
    entry = session(state, key)
    entry["touched"] = time.time()

    if mode == ["remind"]:
        # UserPromptSubmit: a note from the last turn nobody acted on, and
        # drafts that have waited long — each said once.
        notes = []
        noticed = entry.pop("noticed", None)
        if noticed and not drafted_since(ledger, float(noticed.get("at", 0))):
            notes.append(reminder(noticed.get("items") or []))
        old = waiting_long(ledger)
        if old and not entry.get("drafts_said"):
            entry["drafts_said"] = True
            notes.append(drafts_note(old))
        save_state(project, state)
        if notes:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "\n".join(notes),
            }}))
        return 0

    item = observed(event)
    if item is None:
        return 0
    interval = float(os.environ.get("BERRY_WATCH_INTERVAL", "600"))
    now = time.time()
    if now - float(entry["last"]) < interval:
        # Quiet for now, but kept: the next note lists it.
        entry["pending"] = (entry["pending"] + [item])[-MAX_PENDING:]
        save_state(project, state)
        return 0
    items = entry["pending"] + [item]
    entry.update(last=now, pending=[], noticed={"at": now, "items": items})
    save_state(project, state)
    context = note(items, drafts(ledger) if ledger.is_dir() else [], ledger.is_dir())
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 — never break the session
        sys.exit(0)
