#!/usr/bin/env python3
"""UserPromptSubmit hook: when the researcher's message asks about earlier
work, or doubts what the agent said, remind the agent to look in the claims
before answering.

It matches words, not meaning: a list of English phrases — "did we already",
"last time", "contradicts", "are you sure", "hallucinating" — checked
against the message. The agent itself recognizes the same situations from
the recall skill's description, worded any way; this is the safety net for
the common phrasings, and it costs nothing when nothing matches.

Runs in a research project with a claim ledger (claims/ in the nearest
folder up from the session's directory that holds one, else at the git
root: berry_project.py), or with BERRY_WATCH=1. Never blocks. Standard
library only; exit 0 always.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "claims" / "scripts"))
import berry_project  # noqa: E402

# Each: (what the message does, the phrases that show it). Lowercase; \b
# where a word must start or end. Broad on purpose: a reminder too many
# costs one search, a missed one costs a repeated run or a wrong number.
PATTERNS: list[tuple[str, str]] = [
    (
        "asks whether something was done before",
        r"\balready\b|\bhave we\b|\bhaven'?t we\b|\bdid we\b|\bdidn'?t we\b|"
        r"\bhad we\b|\bwe (?:did|ran|tried|tested|checked|computed|measured|"
        r"found|showed|established)\b|\bever (?:tried|tested|checked|run|ran|"
        r"computed|measured|looked)\b|\bbefore\?|\bpreviously\b|\bprevious "
        r"(?:run|result|claim|finding|test|fit|value|calculation|simulation|"
        r"measurement|session|attempt)|\bearlier (?:run|result|claim|finding|"
        r"test|fit|value|calculation|simulation|measurement|session|attempt|"
        r"we)\b|\blast time\b|\blike before\b|\bas before\b|\bthe other day\b|"
        r"\byesterday\b|\blast week\b|\bwhere we left off\b|\bpick up where\b|"
        r"\bcontinue (?:from|where)\b|\bremind me\b|\bwhat did we\b|"
        r"\bdo we (?:know|have)\b|\bis there (?:a|an|any) (?:claim|result|"
        r"record|finding)\b|\bhas (?:this|that|it) been\b|\bbeen (?:checked|"
        r"tested|tried|done|verified|measured|computed|recorded)\b|"
        r"\brecorded\b|\bin the (?:claims|ledger|labbook)\b",
    ),
    (
        "asks whether something contradicts earlier work",
        r"\bcontradict|\binconsistent\b|\binconsistency\b|\bconflicts? with\b|"
        r"\bconflicting\b|\bdisagree|\bat odds\b|\b(?:does ?n[o']?t|do ?n[o']?t)"
        r" (?:match|agree|fit)\b|\bconsistent with\b|\bin line with\b|"
        r"\bsame as (?:before|earlier|last)\b|\bdifferent (?:from|than) "
        r"(?:before|earlier|last)\b|\bchanged since\b|\bcompare (?:it |this )?"
        r"(?:with|to) (?:the )?(?:earlier|previous|last|old)\b",
    ),
    (
        "doubts what you said",
        r"\bhallucinat|\bmade (?:that|this|it|those) up\b|\bmaking (?:that|this|"
        r"it|things) up\b|\bmaking stuff up\b|\bconfus|\bmixed (?:up|them up)\b|"
        r"\bmixing (?:up|them up)\b|\bmisremember|\bare you sure\b|\bsure about "
        r"(?:that|this)\b|\bis (?:that|this) (?:right|true|correct|so)\b|"
        r"\b(?:that'?s|that is|this is) (?:wrong|not right|not true|not correct|"
        r"incorrect)\b|\bwhere (?:does|did) (?:that|this|the) (?:number|value|"
        r"figure|result|come)\b|\bwhere is (?:that|this) from\b|\bsource for "
        r"(?:that|this)\b|\bdouble.?check\b|\bnot what we (?:found|got|saw|"
        r"measured)\b|\bwe never\b|\bi don'?t think we\b|\bthat'?s not what\b",
    ),
]
COMPILED = [(what, re.compile(rx, re.IGNORECASE)) for what, rx in PATTERNS]


def matches(prompt: str) -> list[tuple[str, str]]:
    """(what the message does, the words that showed it), one per kind."""
    found = []
    for what, rx in COMPILED:
        m = rx.search(prompt)
        if m:
            found.append((what, m.group(0)))
    return found


def note(found: list[tuple[str, str]]) -> str:
    said = "; ".join(f"{what} (\"{words}\")" for what, words in found)
    return (
        f"[recall] The researcher's message {said}. Before answering, look "
        "in the claims (skill recall): claims.py recall with the subject, "
        "--exact for a number or name, and the Library's search and "
        "find_literal when berry.science is connected. Read a claim before "
        "relying on it, cite it by id, and say plainly when no claim records "
        "it. If the message is about something else, ignore this note."
    )


def main() -> int:
    try:
        event: dict[str, Any] = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    prompt = event.get("prompt") or event.get("user_prompt") or ""
    if not isinstance(prompt, str) or not prompt.strip():
        return 0
    found = matches(prompt)
    if not found:
        return 0
    project = berry_project.find_project(event.get("cwd") or None)
    if not project.has_ledger and os.environ.get("BERRY_WATCH") != "1":
        return 0
    if not found:
        return 0
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": note(found),
        }
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 — never break the session
        sys.exit(0)
