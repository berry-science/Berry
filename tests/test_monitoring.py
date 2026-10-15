"""Tests for when research-monitoring notices a result, and for the labbook
starting with the first sealed claim — replaying how a real session ran:
a simulation sent to the background, its log read later with tail or the
Read tool, in a project where Berry was enabled but no ledger existed yet.

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "record-claim" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "research-monitoring" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "labbook" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "recall" / "scripts"))

import labbook  # noqa: E402
import overview  # noqa: E402
import watch  # noqa: E402

LOG = "[asymmetric] E/N = 723.191 Hz x h\nnorm drift: 3.3e-13\nenergy drift: 1.8e-05\n"


def call(main, event: dict, *args: str) -> str:
    stdin, out = sys.stdin, io.StringIO()
    sys.stdin = io.StringIO(json.dumps(event))
    try:
        with contextlib.redirect_stdout(out):
            main(*args) if args else main()
    finally:
        sys.stdin = stdin
    return out.getvalue()


def context(printed: str) -> str:
    return json.loads(printed)["hookSpecificOutput"]["additionalContext"] if printed else ""


class Repo(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        os.environ["BERRY_WATCH_INTERVAL"] = "600"
        os.environ.pop("BERRY_WATCH", None)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def ledger(self) -> Path:
        (self.root / "claims").mkdir(exist_ok=True)
        return self.root / "claims"

    def enable_berry(self) -> None:
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text(
            json.dumps({"enabledPlugins": {"berry@berry-science": True}})
        )

    def bash(self, command: str, stdout: str, session: str = "s") -> str:
        return context(call(watch.main, {
            "session_id": session, "cwd": str(self.root), "tool_name": "Bash",
            "tool_input": {"command": command},
            "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False},
        }, []))

    def read(self, path: str, content: str, session: str = "s") -> str:
        return context(call(watch.main, {
            "session_id": session, "cwd": str(self.root), "tool_name": "Read",
            "tool_input": {"file_path": str(self.root / path)},
            "tool_response": {"type": "text", "file": {"filePath": path, "content": content}},
        }, []))

    def remind(self, session: str = "s") -> str:
        return context(call(watch.main, {
            "session_id": session, "cwd": str(self.root), "prompt": "next",
        }, ["remind"]))


class WhereResultsAppearTest(Repo):
    def setUp(self) -> None:
        super().setUp()
        self.ledger()

    def test_a_run_sent_to_the_background_shows_nothing_yet(self) -> None:
        note = self.bash(
            "pixi run python -u scripts/ramp.py > data/ramp.log 2>&1",
            "Command running in background with ID: biwqy9vpd.",
        )
        self.assertEqual(note, "")

    def test_reading_its_log_with_tail_is_seen(self) -> None:
        note = self.bash("cat data/ramp_down.log | tail -12", LOG)
        self.assertIn("$ cat data/ramp_down.log | tail -12", note)
        self.assertIn("norm drift: 3.3e-13", note)

    def test_reading_source_code_with_cat_is_not(self) -> None:
        self.assertEqual(self.bash("cat src/model.py", "x = 1.5\ny = 2.5\n"), "")

    def test_reading_its_log_with_the_read_tool_is_seen(self) -> None:
        note = self.read("data/ramp_down.log", LOG)
        self.assertIn("read " + str(self.root / "data/ramp_down.log"), note)
        self.assertIn("energy drift: 1.8e-05", note)

    def test_reading_code_with_the_read_tool_is_not(self) -> None:
        self.assertEqual(self.read("scripts/ramp.py", "dt = 0.01\nT = 2.5\n"), "")

    def test_fetching_a_background_commands_output_is_seen(self) -> None:
        note = context(call(watch.main, {
            "session_id": "s", "cwd": str(self.root), "tool_name": "BashOutput",
            "tool_input": {"bash_id": "biwqy9vpd"}, "tool_response": {"stdout": LOG},
        }, []))
        self.assertIn("the output of a background command", note)


class QuietAndReminderTest(Repo):
    def setUp(self) -> None:
        super().setUp()
        self.claims = self.ledger()

    def test_results_seen_while_quiet_come_with_the_next_note(self) -> None:
        self.assertIn("ramp_a.log", self.bash("tail data/ramp_a.log", LOG))
        self.assertEqual(self.bash("tail data/ramp_b.log", LOG), "")  # quiet
        os.environ["BERRY_WATCH_INTERVAL"] = "0"
        note = self.bash("tail data/ramp_c.log", LOG)
        self.assertIn("ramp_b.log", note)
        self.assertIn("ramp_c.log", note)

    def test_a_note_nobody_acted_on_comes_back_once(self) -> None:
        self.bash("tail data/ramp_a.log", LOG)
        reminder = self.remind()
        self.assertIn("no claim was drafted since", reminder)
        self.assertIn("ramp_a.log", reminder)
        self.assertEqual(self.remind(), "")

    def test_no_reminder_once_a_claim_was_drafted(self) -> None:
        self.bash("tail data/ramp_a.log", LOG)
        time.sleep(0.01)
        (self.claims / "2026-10-14-ramp").mkdir()
        (self.claims / "2026-10-14-ramp" / "claim.json").write_text("{}")
        self.assertEqual(self.remind(), "")

    def test_sessions_are_kept_apart(self) -> None:
        self.bash("tail data/ramp_a.log", LOG, session="one")
        self.assertEqual(self.remind(session="two"), "")

    def test_an_older_state_file_is_read(self) -> None:
        git_dir = self.root / ".git"
        (git_dir / "berry-watch.json").write_text(json.dumps({"s": time.time() - 3600}))
        self.assertIn("ramp_a.log", self.bash("tail data/ramp_a.log", LOG))


class WaitingDraftsTest(Repo):
    def setUp(self) -> None:
        super().setUp()
        self.claims = self.ledger()
        self.age = watch.DRAFT_AGE

    def tearDown(self) -> None:
        watch.DRAFT_AGE = self.age
        super().tearDown()

    def draft(self, cid: str, age: float) -> None:
        (self.claims / cid).mkdir()
        f = self.claims / cid / "claim.json"
        f.write_text(json.dumps({"id": cid, "status": "draft"}))
        os.utime(f, (time.time() - age, time.time() - age))

    def test_drafts_waiting_long_are_brought_up_once_per_session(self) -> None:
        self.draft("2026-10-14-old", 7200)
        self.draft("2026-10-14-fresh", 60)
        note = self.remind()
        self.assertIn("1 draft(s) waiting for the user to agree: 2026-10-14-old", note)
        self.assertNotIn("fresh", note)
        self.assertEqual(self.remind(), "")
        self.assertIn("2026-10-14-old", self.remind(session="other"))

    def test_no_note_without_old_drafts(self) -> None:
        self.draft("2026-10-14-fresh", 60)
        self.assertEqual(self.remind(), "")


class NoLedgerYetTest(Repo):
    def test_silent_where_berry_is_not_enabled(self) -> None:
        self.assertEqual(self.bash("tail data/ramp.log", LOG), "")
        self.assertEqual(call(overview.main, {"cwd": str(self.root)}), "")

    def test_where_berry_is_enabled_runs_are_noticed_and_the_ledger_offered(self) -> None:
        self.enable_berry()
        note = self.bash("tail data/ramp.log", LOG)
        self.assertIn("norm drift", note)
        self.assertIn("no claim ledger", note)

    def test_the_session_starts_with_a_note_that_there_is_no_ledger(self) -> None:
        self.enable_berry()
        start = context(call(overview.main, {"cwd": str(self.root), "source": "startup"}))
        self.assertIn("Berry is enabled for this project, but it has no claim ledger", start)

    def test_a_globally_enabled_plugin_does_not_count(self) -> None:
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text(json.dumps({"model": "x"}))
        self.assertEqual(self.bash("tail data/ramp.log", LOG), "")


class LabbookStartsWithTheFirstSealedClaimTest(Repo):
    def seal_event(self) -> dict:
        return {"cwd": str(self.root), "tool_name": "Bash",
                "tool_input": {"command": "python3 claims.py seal 2026-10-14-a"}}

    def add_claim(self, cid: str, status: str) -> None:
        folder = self.ledger() / cid
        folder.mkdir()
        (folder / "claim.json").write_text(json.dumps({"id": cid, "status": status, "title": cid}))

    def hook(self) -> str:
        return context(call(labbook.cmd_hook, self.seal_event(), None, None))

    def test_a_draft_alone_starts_nothing(self) -> None:
        self.add_claim("2026-10-14-a", "draft")
        self.assertEqual(self.hook(), "")

    def test_the_first_sealed_claim_asks_for_the_labbook_once(self) -> None:
        self.add_claim("2026-10-14-a", "sealed")
        note = self.hook()
        self.assertIn("1 claim(s) sealed, and this project has no labbook yet", note)
        self.assertIn("labbook.py init", note)
        self.assertEqual(self.hook(), "")  # the same claims: not again
        self.add_claim("2026-10-14-b", "sealed")
        self.assertIn("2 claim(s) sealed", self.hook())

    def test_the_author_is_the_repositorys_never_a_guess(self) -> None:
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Ada Researcher"], check=True)
        self.ledger()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(labbook.main(["--root", str(self.root), "init", "--title", "Ramps"]), 0)
        self.assertIn("Ada Researcher", (self.root / "labbook" / "labbook.tex").read_text())

    def test_an_existing_labbook_is_not_asked_for(self) -> None:
        self.add_claim("2026-10-14-a", "sealed")
        (self.root / "labbook").mkdir()
        (self.root / "labbook" / "labbook.tex").write_text("\\claimbox{2026-10-14-a}\n")
        self.assertNotIn("no labbook yet", self.hook())


if __name__ == "__main__":
    unittest.main()
