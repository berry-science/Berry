"""What a PostToolUse hook event says, whichever agent sent it.

Claude Code and Codex send the same kind of event (`tool_name`,
`tool_input`, `tool_response`, `cwd` on stdin) but describe their tools
differently:

- a shell command is `Bash` with `{"command": "..."}` in Claude Code; Codex
  matches its shell tool as `Bash` too, but may name it otherwise and pass
  the command as a list (`["bash", "-lc", "..."]`);
- a file edit is `Edit`/`Write`/`MultiEdit` with a `file_path` in Claude
  Code, and `apply_patch` in Codex, whose input is a patch naming the files
  (`*** Update File: path`);
- the output of a command is `tool_response.stdout` in Claude Code; other
  agents send a string or another field.

The hooks of this repository (the claims skill's watch.py, labbook.py)
read events only through these functions; which project an event belongs
to — where its ledger is, whether Berry is enabled there — is
berry_project.py's answer. Standard library only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

PATCH_FILE = re.compile(
    r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+?)\s*$", re.MULTILINE
)
SHELL_TOOLS = {"bash", "shell", "local_shell", "exec_command", "unified_exec", "container.exec"}
EDIT_TOOLS = {"edit", "write", "multiedit", "notebookedit", "apply_patch"}
OUTPUT_FIELDS = ("stdout", "output", "aggregated_output", "formatted_output", "content", "text")


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _strings(v)]
    return []


def _is_patch(text: str) -> bool:
    return "*** Begin Patch" in text or bool(PATCH_FILE.search(text))


def tool(event: dict[str, Any]) -> str:
    return str(event.get("tool_name") or "").lower()


def command(event: dict[str, Any]) -> str | None:
    """The shell command a tool call ran, as one string; None if it was not
    a shell command."""
    if tool(event) in EDIT_TOOLS:
        return None
    data = event.get("tool_input") or {}
    if isinstance(data, str):
        raw: Any = data
    else:
        raw = data.get("command", data.get("cmd"))
    if isinstance(raw, (list, tuple)):
        # ["bash", "-lc", "python run.py"]: the script is the last element.
        parts = [str(p) for p in raw]
        if len(parts) >= 3 and parts[1] in ("-c", "-lc", "-ic"):
            raw = parts[-1]
        else:
            raw = " ".join(parts)
    if not isinstance(raw, str) or not raw.strip() or _is_patch(raw):
        return None
    if tool(event) in SHELL_TOOLS or "command" in (data if isinstance(data, dict) else {}):
        return raw
    return None


def edited_paths(event: dict[str, Any]) -> list[Path]:
    """The files a tool call wrote, absolute. Empty for anything else."""
    data = event.get("tool_input") or {}
    cwd = Path(event.get("cwd") or ".")
    found: list[str] = []
    if isinstance(data, dict):
        for key in ("file_path", "notebook_path", "path"):
            if isinstance(data.get(key), str):
                found.append(data[key])
    for text in _strings(data):
        if _is_patch(text):
            found += PATCH_FILE.findall(text)
    return [(cwd / p).resolve() for p in dict.fromkeys(found)]


def output(event: dict[str, Any]) -> str:
    """What the command printed, as far as the event says."""
    response = event.get("tool_response")
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        for key in OUTPUT_FIELDS:
            value = response.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, list):
                text = "\n".join(_strings(value))
                if text:
                    return text
    if isinstance(response, list):
        return "\n".join(_strings(response))
    return ""


def interrupted(event: dict[str, Any]) -> bool:
    response = event.get("tool_response")
    return isinstance(response, dict) and bool(response.get("interrupted"))


READ_TOOLS = {"read"}
# Claude Code's tools that hand back what a background command printed.
BACKGROUND_OUTPUT_TOOLS = {"bashoutput", "taskoutput"}


def read_result(event: dict[str, Any]) -> tuple[str, str] | None:
    """(what was read, its text) for a file read or a background command's
    output fetched later; None for any other tool call. A run started in
    the background prints nothing worth seeing at the time — its results
    arrive here, when they are read."""
    name = tool(event)
    if name in BACKGROUND_OUTPUT_TOOLS:
        return ("the output of a background command", output(event))
    if name not in READ_TOOLS:
        return None
    data = event.get("tool_input") or {}
    path = data.get("file_path") or data.get("path") if isinstance(data, dict) else None
    if not isinstance(path, str):
        return None
    response = event.get("tool_response")
    text = ""
    if isinstance(response, dict) and isinstance(response.get("file"), dict):
        text = str(response["file"].get("content") or "")
    if not text:
        text = output(event)
    return (path, text)
