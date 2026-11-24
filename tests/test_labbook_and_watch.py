"""Tests for skills/labbook/scripts/labbook.py and
skills/claims/scripts/watch.py.

No LaTeX and no vl-convert needed: these check what is generated and when
the hooks speak, not the PDF.

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "labbook" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "claims" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "claims" / "scripts"))

import hook_event  # noqa: E402
import labbook  # noqa: E402
import labbook_core  # noqa: E402
import watch  # noqa: E402


class TexTest(unittest.TestCase):
    def test_special_characters_are_escaped_and_unicode_kept(self) -> None:
        self.assertEqual(
            labbook.tex("50% of x_1 & #2 {a} ~ ^ \\ µm ∫"),
            r"50\% of x\_1 \& \#2 \{a\} \textasciitilde{} \textasciicircum{} "
            r"\textbackslash{} µm ∫",
        )

    def test_a_blank_line_is_a_paragraph(self) -> None:
        self.assertEqual(labbook.tex("one\n\ntwo\nthree"), r"one\par two three")

    def test_the_print_theme_fixes_a_container_width_and_keeps_the_data(self) -> None:
        spec = {"width": "container", "data": {"values": [{"x": 1}]}, "mark": "line"}
        out = labbook.print_theme(spec)
        self.assertEqual(out["width"], labbook.FIGURE_WIDTH)
        self.assertEqual(out["config"]["font"], labbook.FIGURE_FONT)
        self.assertEqual(out["data"], spec["data"])
        self.assertEqual(spec["width"], "container")  # the claim's spec is untouched


class GenerateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        ledger = self.root / "claims"
        for cid, status, cites in (
            ("2026-10-10-b-later", "sealed", "2026-10-09-a-first"),
            ("2026-10-09-a-first", "sealed", None),
            ("2026-10-11-c-draft", "draft", None),
        ):
            (ledger / cid / "evidence").mkdir(parents=True)
            claim = {
                "id": cid,
                "status": status,
                "title": f"Title of {cid} with 50%",
                "statement": "The residual is 31.1 µm.",
                "holds_when": "Simulation.",
                "claim_type": "negative_result",
                "evidence": [],
                "citations": [{"local": cites, "relation": "uses"}] if cites else [],
                "seal": {"sha256": "ab" * 32} if status == "sealed" else None,
            }
            (ledger / cid / "claim.json").write_text(json.dumps(claim))
        self.lb = labbook.Labbook(self.root)
        self.lb.dir.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_claims_come_after_what_they_rest_on(self) -> None:
        claims = [{"id": cid, **c} for cid, c in sorted(self.lb.ledger.all().items())]
        self.assertEqual(
            labbook_core.claim_order(claims),
            ["2026-10-09-a-first", "2026-10-10-b-later", "2026-10-11-c-draft"],
        )

    def test_generated_tex_defines_every_claim_and_is_stable(self) -> None:
        labbook.generate(self.lb, figures=False)
        first = self.lb.gen.read_text()
        self.assertIn(r"\berrydefclaim{2026-10-09-a-first}{Title of 2026-10-09-a-first with 50\%}", first)
        self.assertIn(r"\berryReluses{} \claimref{2026-10-09-a-first}", first)
        self.assertIn(r"\berryTypenegativeresult{}", first)
        self.assertIn(r"\berryDraft", first)
        labbook.generate(self.lb, figures=False)
        self.assertEqual(self.lb.gen.read_text(), first)  # no churn in git

    def test_check_finds_unknown_ids_and_sealed_claims_not_shown(self) -> None:
        self.lb.tex.write_text(
            "\\claimbox{2026-10-09-a-first}\n% \\claimbox{2026-10-10-b-later}\n"
            "\\claimbox{2020-01-01-nothing}\n"
        )
        errors, missing = labbook.check(self.lb)
        self.assertEqual(len(errors), 1)
        self.assertIn("2020-01-01-nothing", errors[0])
        # Commented out is not shown; a draft is not required.
        self.assertEqual(missing, ["2026-10-10-b-later"])

    def test_a_step_without_a_claim_fails_check(self) -> None:
        self.lb.tex.write_text(
            "\\section*{Where things stand}\nProse is fine here.\n"
            "\\section{Phase 0 documented}\nA long chapter of prose.\n"
            "\\section{Residual measured}\n\\claimbox{2026-10-09-a-first}\n"
            "% \\section{A commented-out step}\n"
            "\\section*{Open points and follow-up questions}\n- next\n"
            "\\section*{Notes}\nWhat the researcher asked to keep.\n"
            "\\appendix\n\\section{Conventions}\n\\berryconventions\n"
        )
        errors, _ = labbook.check(self.lb)
        claimless = [e for e in errors if labbook.NO_CLAIM in e]
        self.assertEqual(len(claimless), 1, errors)
        self.assertIn("'Phase 0 documented'", claimless[0])

    def test_notes_come_last_and_only_when_there_are_any(self) -> None:
        book = {"title": "T", "language": "en", "open_points": "- open", "notes": "Kept."}
        out = labbook_core.document(book, [])
        self.assertLess(out.index("Open points"), out.index("\\section*{Notes}"))
        self.assertLess(out.index("\\section*{Notes}"), out.index("\\appendix"))
        self.assertNotIn("Notes}", labbook_core.document({**book, "notes": None}, []))
        self.assertIn("\\section*{Notizen}", labbook_core.document({**book, "language": "de"}, []))

    def test_the_hook_ignores_edits_outside_the_ledger_and_labbook(self) -> None:
        event = {"tool_name": "Edit", "tool_input": {"file_path": str(self.root / "src" / "x.py")}}
        self.assertFalse(labbook.relevant(self.lb, event))
        event["tool_input"]["file_path"] = str(self.root / "claims" / "x" / "claim.json")
        self.assertTrue(labbook.relevant(self.lb, event))
        event["tool_input"]["file_path"] = str(self.lb.gen)
        self.assertFalse(labbook.relevant(self.lb, event))
        seal = {"tool_name": "Bash", "tool_input": {"command": "python3 claims.py seal 2026-x"}}
        self.assertTrue(labbook.relevant(self.lb, seal))
        # Publishing records the Library link the claim's box shows.
        publish = {"tool_name": "Bash", "tool_input": {"command": "python3 claims.py publish --ready"}}
        self.assertTrue(labbook.relevant(self.lb, publish))
        other = {"tool_name": "Bash", "tool_input": {"command": "python3 claims.py check"}}
        self.assertFalse(labbook.relevant(self.lb, other))


class WatchTest(unittest.TestCase):
    def test_a_run_with_results_is_noticed(self) -> None:
        lines = watch.looks_like_a_run(
            "pixi run python sim.py --ramp sta", "done\nresidual 0.009 um\nrms 3.1e-3\n"
        )
        self.assertEqual(lines, ["residual 0.009 um", "rms 3.1e-3"])

    def test_tools_and_tests_are_not_runs(self) -> None:
        for command in (
            "git log --stat",
            "ls -la",
            "python -m pytest -q",
            "python3 claims.py check",
            "cd src && grep -n 1.5 x.py",
        ):
            self.assertEqual(watch.looks_like_a_run(command, "1.5 2.5 3.5"), [], command)

    def test_one_number_is_not_enough(self) -> None:
        self.assertEqual(watch.looks_like_a_run("python run.py", "took 1.2 s"), [])

    def test_env_assignments_before_the_command_are_skipped(self) -> None:
        self.assertEqual(watch.first_word("OMP_NUM_THREADS=4 python run.py"), "python")

    def test_the_hook_is_silent_outside_a_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event = {
                "tool_name": "Bash",
                "cwd": tmp,
                "tool_input": {"command": "python run.py"},
                "tool_response": {"stdout": "1.5 2.5"},
            }
            out = io.StringIO()
            stdin = sys.stdin
            sys.stdin = io.StringIO(json.dumps(event))
            try:
                with redirect_stdout(out):
                    watch.main()
            finally:
                sys.stdin = stdin
            self.assertEqual(out.getvalue(), "")


class CoreTest(unittest.TestCase):
    """The generator the Library shares: what an agent writes must not
    reach LaTeX as commands."""

    def test_markdown_escapes_every_command_outside_allowed_math(self) -> None:
        out = labbook_core.markdown(
            "\\input{/etc/passwd} \\write18{rm -rf /} \\directlua{os.exit()} $\\input{x}$"
        )
        self.assertNotRegex(out, r"(?<!textbackslash\{\})\\(input|write18|directlua)")
        self.assertIn(r"\textbackslash{}input", out)

    def test_markdown_keeps_allowed_math_and_simple_formatting(self) -> None:
        out = labbook_core.markdown(
            "With $\\omega = 2\\pi f$ and **bold**, *italic*, `code`.\n\n- one\n- two"
        )
        self.assertIn(r"$\omega = 2\pi f$", out)
        self.assertIn(r"\textbf{bold}", out)
        self.assertIn(r"\emph{italic}", out)
        self.assertIn(r"\texttt{code}", out)
        self.assertIn("\\begin{itemize}", out)

    def test_inline_formatting_keeps_the_spaces_around_it(self) -> None:
        out = labbook_core.markdown("with $x$ and **this** here")
        self.assertEqual(out, r"with $x$ and \textbf{this} here")

    def test_a_claim_reference_becomes_a_link_and_only_a_valid_id_does(self) -> None:
        out = labbook_core.markdown("see [[claim:3f0b1a2c-1111-2222-3333-444455556666]]")
        self.assertIn(r"\claimref{3f0b1a2c-1111-2222-3333-444455556666}", out)
        with self.assertRaises(ValueError):
            labbook_core.macro_id("x}\\input{y")

    def test_urls_cannot_close_the_href(self) -> None:
        self.assertNotIn("}", labbook_core.tex_url("https://x.org/}\\input{a}"))

    def test_a_document_from_steps(self) -> None:
        cid = "3f0b1a2c-1111-2222-3333-444455556666"
        doc = labbook_core.document(
            {"title": "Trap & transport", "language": "de",
             "where_things_stand": "Fast fertig.", "open_points": "- Rauschen?"},
            [{"heading": "Erster Schritt", "why": "Weil.", "what": "So.",
              "means": "Also.", "claim_id": cid, "sources": []}],
        )
        self.assertIn(r"\title{Trap \& transport}", doc)
        self.assertIn(r"\usepackage[ngerman]{babel}", doc)
        self.assertIn(r"\section*{Offene Punkte und Folgefragen}", doc)
        self.assertIn(rf"\claimbox{{{cid}}}", doc)
        self.assertLess(doc.index("Weil."), doc.index(r"\claimbox"))


class CodexEventTest(unittest.TestCase):
    """Codex sends the same hook events with its own tool shapes."""

    PATCH = (
        "*** Begin Patch\n*** Update File: claims/2026-x/claim.json\n@@\n-a\n+b\n"
        "*** Add File: src/new.py\n+print(1)\n*** End Patch\n"
    )

    def test_an_apply_patch_names_its_files_and_is_no_command(self) -> None:
        event = {"tool_name": "apply_patch", "cwd": "/repo", "tool_input": {"input": self.PATCH}}
        self.assertIsNone(hook_event.command(event))
        self.assertEqual(
            [str(p) for p in hook_event.edited_paths(event)],
            [str(Path("/repo/claims/2026-x/claim.json").resolve()),
             str(Path("/repo/src/new.py").resolve())],
        )
        # A patch passed under "command" is still a patch, not a shell run.
        event["tool_input"] = {"command": self.PATCH}
        self.assertIsNone(hook_event.command(event))

    def test_a_shell_command_as_a_list_is_the_script(self) -> None:
        event = {"tool_name": "shell", "tool_input": {"command": ["bash", "-lc", "python run.py"]}}
        self.assertEqual(hook_event.command(event), "python run.py")

    def test_output_comes_from_whichever_field_carries_it(self) -> None:
        for response in ("residual 0.009", {"output": "residual 0.009"},
                         {"stdout": "residual 0.009"}, {"aggregated_output": "residual 0.009"}):
            self.assertEqual(hook_event.output({"tool_response": response}), "residual 0.009")

    def test_the_labbook_hook_sees_a_codex_edit_in_the_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lb = labbook.Labbook(Path(tmp))
            event = {"tool_name": "apply_patch", "cwd": tmp, "tool_input": {"input": self.PATCH}}
            self.assertTrue(labbook.relevant(lb, event))
            seal = {"tool_name": "shell", "cwd": tmp,
                    "tool_input": {"command": ["bash", "-lc", "python3 claims.py seal 2026-x"]}}
            self.assertTrue(labbook.relevant(lb, seal))

    def test_the_monitor_notices_a_codex_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            (Path(tmp) / "claims").mkdir()
            event = {
                "tool_name": "exec_command",
                "cwd": tmp,
                "session_id": "codex-1",
                "tool_input": {"command": ["bash", "-lc", "python sim.py"]},
                "tool_response": "residual 0.009 um\nrms 0.0031 um\n",
            }
            out = io.StringIO()
            stdin, sys.stdin = sys.stdin, io.StringIO(json.dumps(event))
            try:
                with redirect_stdout(out):
                    watch.main()
            finally:
                sys.stdin = stdin
            note = json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
            self.assertIn("residual 0.009 um", note)
            self.assertIn("berry:claim-checker", note)


class PluginManifestTest(unittest.TestCase):
    def test_the_claude_code_and_codex_manifests_agree(self) -> None:
        claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        codex = json.loads((ROOT / "plugin.json").read_text())
        for key in ("name", "version", "description", "license", "repository"):
            self.assertEqual(claude[key], codex[key], key)
        hooks = codex["extensions"]["com.openai"]["hooks"]
        self.assertTrue((ROOT / hooks).is_file())

    def test_the_codex_marketplace_lists_the_plugin_at_its_manifest(self) -> None:
        market = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
        (entry,) = market["plugins"]
        codex = json.loads((ROOT / "plugin.json").read_text())
        self.assertEqual(entry["name"], codex["name"])
        self.assertEqual(entry["source"]["source"], "local")
        self.assertTrue((ROOT / entry["source"]["path"] / "plugin.json").is_file())

    def test_every_background_agent_has_its_instructions_in_a_skill(self) -> None:
        for agent in (ROOT / "agents").glob("*.md"):
            text = agent.read_text()
            ref = re.search(r"`(skills/[^`]+/references/[^`]+\.md)`", text)
            self.assertIsNotNone(ref, agent.name)
            self.assertTrue((ROOT / ref.group(1)).is_file(), ref.group(1))


if __name__ == "__main__":
    unittest.main()
