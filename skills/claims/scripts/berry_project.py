"""Where a research project keeps its claim ledger — one answer for
claims.py and every hook.

A research repository can hold more than one project, each with its own
ledger: lab/claims/ for the simulation, lab/ramp_study/claims/
for a separate project in a subdirectory. The project root is the folder
the ledger sits in; its labbook is beside it:

    <project root>/claims/     the ledger
    <project root>/labbook/    the labbook

The ledger is found in this order:

1. `--root` (claims.py only): the ledger folder itself;
2. $BERRY_CLAIMS_DIR: the ledger folder itself;
3. walking up from the starting directory to the git toplevel, inclusive:
   the nearest directory that holds a claims/ ledger, or that switches the
   berry plugin on in its own .claude/settings*.json. A folder named claims
   counts as a ledger only if it holds conventions.json, README.md or a
   claim (*/claim.json, */claim.md), so a stray claims/ is not taken for one;
4. claims/ at the git toplevel (the start directory outside git), as
   before, so a single-project repository behaves the same.

The starting directory is the hook event's cwd, or the folder of the file a
tool call edited. Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

LEDGER = "claims"
LABBOOK = "labbook"
# What makes a claims/ folder a ledger rather than any folder of that name.
LEDGER_FILES = ("conventions.json", "README.md")
CLAIM_FILES = ("claim.json", "claim.md")


def git(*args: str, cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def git_toplevel(start: Path) -> Path | None:
    top = git("rev-parse", "--show-toplevel", cwd=start)
    return Path(top).resolve() if top else None


def start_dir(path: str | Path | None) -> Path:
    """The directory to start from: `path` if it is one, else the nearest
    existing folder above it (a file's folder; a deleted file's)."""
    p = Path(path or os.getcwd()).expanduser()
    p = p if p.is_absolute() else Path.cwd() / p
    while not p.is_dir() and p.parent != p:
        p = p.parent
    return p.resolve()


def is_ledger(folder: Path) -> bool:
    """Is this folder a claim ledger, and not just a folder named claims?"""
    if not folder.is_dir():
        return False
    if any((folder / name).is_file() for name in LEDGER_FILES):
        return True
    try:
        return any(
            (sub / name).is_file()
            for sub in folder.iterdir() if sub.is_dir()
            for name in CLAIM_FILES
        )
    except OSError:
        return False


def berry_enabled_here(root: Path) -> bool:
    """Is the berry plugin switched on in this folder's own settings
    (.claude/settings.json or settings.local.json)? Then the project is
    meant to keep a ledger, even before it has one. A plugin enabled only
    in the user's global settings does not count: that would make every
    repository look like research."""
    for name in ("settings.json", "settings.local.json"):
        file = root / ".claude" / name
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        plugins = data.get("enabledPlugins") if isinstance(data, dict) else None
        if isinstance(plugins, dict) and any(
            str(k).split("@")[0] == "berry" and v for k, v in plugins.items()
        ):
            return True
    return False


@dataclass(frozen=True)
class Project:
    root: Path          # the project root: claims/ and labbook/ sit here
    ledger: Path        # the ledger folder (usually root / "claims")
    top: Path | None    # the git toplevel, None outside a repository
    how: str            # "root" (--root), "env", "walk" or "fallback"

    @property
    def labbook(self) -> Path:
        return self.root / LABBOOK

    @property
    def has_ledger(self) -> bool:
        return self.ledger.is_dir()

    @property
    def enabled(self) -> bool:
        return berry_enabled_here(self.root)

    def state_file(self, name: str) -> Path:
        """A file for this machine's own state (rate limits, markers), never
        committed: in the git directory, else $TMPDIR. One per project, so two
        projects in one repository do not share it; the project at the git
        toplevel keeps the plain `name`, as before."""
        git_dir = git("rev-parse", "--absolute-git-dir", cwd=self.root) if self.root.is_dir() else None
        base = Path(git_dir) if git_dir else Path(os.environ.get("TMPDIR", "/tmp"))
        if self.top is not None and self.root.resolve() == self.top:
            return base / name
        tag = hashlib.sha256(str(self.root.resolve()).encode()).hexdigest()[:12]
        stem, dot, suffix = name.partition(".")
        return base / f"{stem}-{tag}{dot}{suffix}"


def _given(ledger: str | Path, how: str) -> Project:
    folder = Path(ledger).expanduser().resolve()
    near = folder if folder.is_dir() else start_dir(folder)
    return Project(root=folder.parent, ledger=folder, top=git_toplevel(near), how=how)


def find_project(start: str | Path | None = None, given: str | Path | None = None) -> Project:
    """The project that `start` (a folder or a file; default: the current
    directory) belongs to. `given` is claims.py's --root."""
    if given:
        return _given(given, "root")
    if os.environ.get("BERRY_CLAIMS_DIR"):
        return _given(os.environ["BERRY_CLAIMS_DIR"], "env")
    here = start_dir(start)
    top = git_toplevel(here)
    chain = [here]
    if top is not None and (here == top or top in here.parents):
        chain = [here, *[p for p in here.parents if p == top or top in p.parents]]
    for folder in chain:
        if is_ledger(folder / LEDGER) or berry_enabled_here(folder):
            return Project(root=folder, ledger=folder / LEDGER, top=top, how="walk")
    base = top or here
    return Project(root=base, ledger=base / LEDGER, top=top, how="fallback")


def find_ledger(start: str | Path | None = None, given: str | Path | None = None) -> Path:
    """The ledger folder only (it may not exist yet)."""
    return find_project(start, given).ledger
