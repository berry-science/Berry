"""Tests for where the ledger is found (skills/claims/scripts/
berry_project.py), and that claims.py and every hook find the same one.

A repository can hold several projects, each with its own claims/ and
labbook/ in a subdirectory. The fixture is a git repository with

    proj_a/claims/     a ledger (one sealed claim, one draft)
    proj_a/src/
    proj_b/src/        no ledger
                       nothing at the toplevel

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
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "claims" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "claims" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "labbook" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "recall" / "scripts"))

import berry_project  # noqa: E402
import labbook  # noqa: E402
import nudge  # noqa: E402
import overview  # noqa: E402
import watch  # noqa: E402

CLAIMS_PY = ROOT / "skills" / "claims" / "scripts" / "claims.py"
FORMALIZE_PY = ROOT / "skills" / "formalize-derivation" / "scripts" / "formalize.py"
LOG = "[asymmetric] E/N = 723.191 Hz x h\nnorm drift: 3.3e-13\nenergy drift: 1.8e-05\n"
SEALED = "2026-10-14-floquet-gap"
DRAFT = "2026-10-15-floquet-drift"


def call(main, event: dict, *args) -> str:
    stdin, out = sys.stdin, io.StringIO()
    sys.stdin = io.StringIO(json.dumps(event))
    try:
        with contextlib.redirect_stdout(out):
            main(*args)
    finally:
        sys.stdin = stdin
    return out.getvalue()


def context(printed: str) -> str:
    return json.loads(printed)["hookSpecificOutput"]["additionalContext"] if printed else ""


def add_claim(ledger: Path, cid: str, status: str) -> None:
    (ledger / cid / "evidence").mkdir(parents=True)
    (ledger / cid / "claim.json").write_text(json.dumps({
        "id": cid, "status": status, "title": f"Title of {cid}",
        "statement": "s", "holds_when": "h", "claim_type": "result",
        "evidence": [], "citations": [],
    }))


class Projects(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.top = Path(self.tmp.name).resolve()
        subprocess.run(["git", "init", "-q", str(self.top)], check=True)
        self.a = self.top / "proj_a"
        self.b = self.top / "proj_b"
        for d in (self.a / "src", self.b / "src"):
            d.mkdir(parents=True)
        add_claim(self.a / "claims", SEALED, "sealed")
        add_claim(self.a / "claims", DRAFT, "draft")
        self.env = mock.patch.dict(os.environ, {"BERRY_WATCH_INTERVAL": "600"})
        self.env.start()
        for name in ("BERRY_CLAIMS_DIR", "BERRY_WATCH"):
            os.environ.pop(name, None)

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    # --- each hook, as Claude Code calls it ---

    def overview(self, cwd: Path) -> str:
        return context(call(overview.main, {"cwd": str(cwd), "hook_event_name": "SessionStart"}))

    def nudge(self, cwd: Path) -> str:
        return context(call(nudge.main, {"cwd": str(cwd), "prompt": "did we already run this?"}))

    def watch(self, cwd: Path, session: str = "s") -> str:
        return context(call(watch.main, {
            "session_id": session, "cwd": str(cwd), "tool_name": "Bash",
            "tool_input": {"command": "python sim.py"},
            "tool_response": {"stdout": LOG, "stderr": "", "interrupted": False},
        }, []))

    def remind(self, cwd: Path, session: str = "s") -> str:
        with mock.patch.object(watch, "DRAFT_AGE", 0):
            return context(call(watch.main, {
                "session_id": session, "cwd": str(cwd), "prompt": "next",
            }, ["remind"]))

    def labbook_hook(self, cwd: Path, **event) -> str:
        event = {"cwd": str(cwd), "tool_name": "Bash",
                 "tool_input": {"command": f"python3 claims.py seal {SEALED}"}, **event}
        return context(call(labbook.cmd_hook, event, None, None))

    def claims_new(self, cwd: Path, title: str = "A new finding") -> None:
        env = {k: v for k, v in os.environ.items() if k != "BERRY_CLAIMS_DIR"}
        proc = subprocess.run([sys.executable, str(CLAIMS_PY), "new", title],
                              cwd=cwd, env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def claim_ids(self, ledger: Path) -> set[str]:
        return {p.name for p in ledger.iterdir() if p.is_dir()} if ledger.is_dir() else set()

    def forget_labbook_marker(self, root: Path) -> None:
        berry_project.find_project(root).state_file("berry-labbook-start").unlink(missing_ok=True)


class SubdirectoryProjectTest(Projects):
    def test_the_walk_finds_the_nearest_ledger(self) -> None:
        for cwd in (self.a, self.a / "src", self.a / "claims" / SEALED / "evidence"):
            p = berry_project.find_project(cwd)
            self.assertEqual((p.root, p.ledger, p.how), (self.a, self.a / "claims", "walk"), cwd)
            self.assertEqual(p.labbook, self.a / "labbook")
        file = berry_project.find_project(self.a / "src" / "not_yet_written.py")
        self.assertEqual(file.root, self.a)

    def test_every_hook_finds_the_ledger_from_the_project_and_below(self) -> None:
        for cwd in (self.a, self.a / "src"):
            with self.subTest(cwd=cwd):
                text = self.overview(cwd)
                self.assertIn(str(self.a / "claims"), text)
                self.assertIn(f"Title of {SEALED}", text)
                self.assertIn("[recall]", self.nudge(cwd))
                session = f"s-{cwd.name}"
                note = self.watch(cwd, session)
                self.assertIn("norm drift: 3.3e-13", note)
                self.assertIn(DRAFT, note)  # the drafts of proj_a's ledger
                self.assertIn(DRAFT, self.remind(cwd, session))
                self.forget_labbook_marker(cwd)
                note = self.labbook_hook(cwd)
                self.assertIn("1 claim(s) sealed", note)
                self.assertIn(f"labbook.py --root {self.a} init", note)

    def test_formalize_finds_the_claim_in_the_projects_ledger(self) -> None:
        """formalize.py takes claim ids and once looked only at the top's
        claims/: from inside a project it reported "no claim"."""
        env = {k: v for k, v in os.environ.items() if k != "BERRY_CLAIMS_DIR"}
        for cwd in (self.a, self.a / "src"):
            with self.subTest(cwd=cwd):
                proc = subprocess.run(
                    [sys.executable, str(FORMALIZE_PY), "cover", SEALED],
                    cwd=cwd, env=env, capture_output=True, text=True,
                )
                out = proc.stdout + proc.stderr
                self.assertNotIn("no claim", out)
                self.assertEqual(proc.returncode, 0, out)

    def test_the_gitignore_advice_works_for_a_project_below_the_top(self) -> None:
        """A gitignore pattern with a slash is relative to its file's folder:
        `!claims/**` in the top .gitignore re-includes nothing in proj_b/.
        The advice names the ledger from the folder of the .gitignore that
        holds the rule, and following it re-includes the files."""
        env = {k: v for k, v in os.environ.items() if k != "BERRY_CLAIMS_DIR"}

        def claims(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, str(CLAIMS_PY), *args],
                                  cwd=self.b, env=env, capture_output=True, text=True)

        self.assertEqual(claims("init").returncode, 0)
        cid = claims("new", "A finding").stdout.splitlines()[0]
        (self.top / ".gitignore").write_text("*.md\n")
        out = claims("check", cid).stdout
        self.assertIn("`!proj_b/claims/**` to .gitignore", out)
        with (self.top / ".gitignore").open("a") as f:
            f.write("!proj_b/claims/**\n")
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", f"proj_b/claims/{cid}/claim.md"], cwd=self.top
        )
        self.assertEqual(ignored.returncode, 1)  # 1: not ignored
        self.assertNotIn("ignored by git", claims("check", cid).stdout)

    def test_init_starts_a_ledger_in_a_project_without_one(self) -> None:
        """Without a ledger or a Berry setting in proj_b, its first claim would
        go to the top of the repository; `claims.py init` puts it in proj_b."""
        env = {k: v for k, v in os.environ.items() if k != "BERRY_CLAIMS_DIR"}
        proc = subprocess.run([sys.executable, str(CLAIMS_PY), "init"],
                              cwd=self.b, env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.b / "claims" / "README.md").is_file())
        self.claims_new(self.b / "src")
        self.assertEqual(len(self.claim_ids(self.b / "claims")), 1)
        self.assertFalse((self.top / "claims").exists())

    def test_claims_py_from_inside_the_project_uses_its_ledger(self) -> None:
        before = self.claim_ids(self.a / "claims")
        self.claims_new(self.a / "src")
        self.assertEqual(len(self.claim_ids(self.a / "claims") - before), 1)
        self.assertFalse((self.top / "claims").exists())
        self.assertFalse((self.a / "src" / "claims").exists())

    def test_outside_the_project_every_hook_is_silent(self) -> None:
        for cwd in (self.b, self.b / "src", self.top):
            with self.subTest(cwd=cwd):
                self.assertEqual(self.overview(cwd), "")
                self.assertEqual(self.nudge(cwd), "")
                self.assertEqual(self.watch(cwd), "")
                self.assertEqual(self.remind(cwd), "")
                self.assertEqual(self.labbook_hook(cwd), "")
        self.assertFalse((self.top / "labbook").exists())

    def test_the_watch_state_is_kept_per_project(self) -> None:
        self.assertIn("norm drift", self.watch(self.a))
        add_claim(self.b / "claims", "2026-10-16-other", "sealed")
        # proj_a's note was just given; proj_b has its own rate limit.
        self.assertIn("norm drift", self.watch(self.b))
        self.assertEqual(self.watch(self.a), "")
        files = {berry_project.find_project(d).state_file("berry-watch.json") for d in (self.a, self.b)}
        self.assertEqual(len(files), 2)
        self.assertTrue(all(f.is_file() for f in files))
        self.assertFalse((self.top / ".git" / "berry-watch.json").exists())

    def test_the_labbook_hook_rebuilds_the_labbook_of_the_edited_file(self) -> None:
        (self.a / "labbook").mkdir()
        (self.a / "labbook" / "labbook.tex").write_text(f"\\claimbox{{{SEALED}}}\n")
        edited = self.a / "claims" / SEALED / "evidence" / "01-reasoning.md"
        edited.write_text("why", encoding="utf-8")
        event = {"tool_name": "Edit", "tool_input": {"file_path": str(edited)}}
        with mock.patch.object(labbook, "compile_pdf", return_value=None) as compiled:
            self.labbook_hook(self.top, **event)
        compiled.assert_called_once()
        self.assertTrue((self.a / "labbook" / "claims.gen.tex").is_file())
        self.assertFalse((self.top / "labbook").exists())

    def test_brand_new_ledger_goes_where_berry_is_enabled(self) -> None:
        (self.b / ".claude").mkdir()
        (self.b / ".claude" / "settings.json").write_text(
            json.dumps({"enabledPlugins": {"berry@berry-science": True}})
        )
        self.assertIn("no claim ledger", self.overview(self.b / "src"))
        self.claims_new(self.b / "src")
        self.assertEqual(len(self.claim_ids(self.b / "claims")), 1)
        self.assertFalse((self.top / "claims").exists())


class WhichLedgerWinsTest(Projects):
    def test_the_nearest_ledger_wins_over_the_toplevel(self) -> None:
        add_claim(self.top / "claims", "2026-10-01-top", "sealed")
        self.assertEqual(berry_project.find_project(self.a / "src").ledger, self.a / "claims")
        self.assertEqual(berry_project.find_project(self.b / "src").ledger, self.top / "claims")
        self.assertEqual(berry_project.find_project(self.top).ledger, self.top / "claims")
        self.assertIn(f"Title of {SEALED}", self.overview(self.a / "src"))
        self.assertNotIn("2026-10-01-top", self.overview(self.a / "src"))
        self.assertIn("Title of 2026-10-01-top", self.overview(self.b))

    def test_berry_claims_dir_overrides_the_walk(self) -> None:
        other = self.top / "elsewhere" / "ledger"
        add_claim(other, "2026-10-02-env", "sealed")
        with mock.patch.dict(os.environ, {"BERRY_CLAIMS_DIR": str(other)}):
            p = berry_project.find_project(self.a / "src")
            self.assertEqual((p.ledger, p.root, p.how), (other, other.parent, "env"))
            text = self.overview(self.a)
            self.assertIn("Title of 2026-10-02-env", text)
            self.assertNotIn(SEALED, text)
            self.assertIn("[recall]", self.nudge(self.b))
        self.assertEqual(
            berry_project.find_project(self.a, given=str(other)).ledger, other
        )

    def test_a_stray_claims_folder_is_not_a_ledger(self) -> None:
        stray = self.b / "claims"
        (stray / "plots").mkdir(parents=True)
        (stray / "notes.txt").write_text("not a ledger")
        self.assertFalse(berry_project.is_ledger(stray))
        p = berry_project.find_project(self.b / "src")
        self.assertEqual((p.root, p.how), (self.top, "fallback"))
        self.assertEqual(self.overview(self.b), "")
        self.assertEqual(self.watch(self.b), "")
        for marker in ("README.md", "conventions.json"):
            with self.subTest(marker=marker):
                (stray / marker).write_text("{}")
                self.assertTrue(berry_project.is_ledger(stray))
                (stray / marker).unlink()


class SingleProjectTest(unittest.TestCase):
    """claims/ at the toplevel: everything as before this resolver."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.top = Path(self.tmp.name).resolve()
        subprocess.run(["git", "init", "-q", str(self.top)], check=True)
        (self.top / "src" / "deep").mkdir(parents=True)
        add_claim(self.top / "claims", SEALED, "sealed")
        self.env = mock.patch.dict(os.environ, {"BERRY_WATCH_INTERVAL": "600"})
        self.env.start()
        for name in ("BERRY_CLAIMS_DIR", "BERRY_WATCH"):
            os.environ.pop(name, None)

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_the_toplevel_ledger_from_anywhere_in_the_repository(self) -> None:
        for cwd in (self.top, self.top / "src" / "deep"):
            p = berry_project.find_project(cwd)
            self.assertEqual((p.root, p.ledger), (self.top, self.top / "claims"), cwd)
            text = context(call(overview.main, {"cwd": str(cwd)}))
            self.assertIn(f"Title of {SEALED}", text)

    def test_the_state_files_keep_their_old_names(self) -> None:
        p = berry_project.find_project(self.top / "src")
        self.assertEqual(p.state_file("berry-watch.json"), self.top / ".git" / "berry-watch.json")
        note = context(call(watch.main, {
            "session_id": "s", "cwd": str(self.top / "src"), "tool_name": "Bash",
            "tool_input": {"command": "python sim.py"},
            "tool_response": {"stdout": LOG, "stderr": "", "interrupted": False},
        }, []))
        self.assertIn("norm drift", note)
        self.assertTrue((self.top / ".git" / "berry-watch.json").is_file())

    def test_an_empty_claims_folder_at_the_toplevel_still_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp).resolve()
            subprocess.run(["git", "init", "-q", str(top)], check=True)
            (top / "claims").mkdir()
            p = berry_project.find_project(top)
            self.assertEqual((p.ledger, p.how, p.has_ledger), (top / "claims", "fallback", True))

    def test_a_new_ledger_starts_at_the_toplevel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp).resolve()
            subprocess.run(["git", "init", "-q", str(top)], check=True)
            (top / "src").mkdir()
            env = {k: v for k, v in os.environ.items() if k != "BERRY_CLAIMS_DIR"}
            proc = subprocess.run([sys.executable, str(CLAIMS_PY), "new", "First"],
                                  cwd=top / "src", env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(len([d for d in (top / "claims").iterdir() if d.is_dir()]), 1)


if __name__ == "__main__":
    unittest.main()
