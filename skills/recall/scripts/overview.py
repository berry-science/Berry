#!/usr/bin/env python3
"""SessionStart hook: the titles of every claim, so the agent knows what the
project has established before the researcher asks.

Runs when a session starts, resumes, is cleared or is compacted — a
compaction summary keeps the gist and drops exactly this kind of detail —
in a research project with a claim ledger: claims/ in the nearest folder
up from the session's directory that holds one, else at the git root
(berry_project.py — a repository can hold several projects). It
hands the agent every claim's title, newest first, and the drafts waiting
for the researcher. Titles only: the claims themselves are read when a
topic comes up (skill recall), not now.

No cap on the number of claims: a title is one line, and a title missing
from the list is a topic the agent will not think to look up.

Standard library only. Exit 0 always: a hook that breaks the session is
worse than none.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "claims" / "scripts"))
import berry_project  # noqa: E402
import claims  # noqa: E402


def overview(ledger: claims.Ledger) -> str | None:
    titles = claims.claim_titles(ledger)
    if not titles:
        return None
    waiting = [cid for cid, c in ledger.all().items() if c.get("status") == "draft"]
    text = (
        f"[recall] The project's claim ledger ({ledger.root}) holds "
        f"{len(titles)} claim(s), newest first. Titles only — read a claim "
        "before relying on it. When the work touches one of these topics, "
        "or you are unsure whether something was already run, shown or "
        "assumed, search the claims first (skill recall: claims.py recall, "
        "and the Library's search when berry.science is connected).\n"
        + "\n".join(f"  {t}" for t in titles)
    )
    if waiting:
        text += (
            f"\nDrafts not yet sealed ({len(waiting)}; claims.py pending says why): "
            + ", ".join(sorted(waiting))
            + "."
        )
    return text


# Berry switched on for this project, and nothing recorded yet: said once
# per session, so the plugin cannot sit there silently doing nothing.
NO_LEDGER = (
    "[berry] Berry is enabled for this project, but it has no claim ledger "
    "(claims/) yet, so nothing is being recorded. At a natural moment — not "
    "in the middle of the user's task — offer once to start it: the first "
    "finding recorded as a claim starts the ledger (skill claims; "
    "claims.py new creates claims/), and after the first sealed claim the "
    "labbook is created (skill labbook). Until then, notice findings as "
    "usual (skill claims) and offer to record them."
)


def main() -> int:
    try:
        event: dict[str, Any] = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        event = {}
    project = berry_project.find_project(event.get("cwd") or None)
    ledger = claims.Ledger(project.ledger)
    if not project.has_ledger:
        text = NO_LEDGER if project.enabled else None
    else:
        text = overview(ledger)
    if text is None:
        return 0
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 — never break the session
        sys.exit(0)
