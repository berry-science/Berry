"""Tests for the recall skill: `claims.py recall` and its two hooks,
skills/recall/scripts/overview.py (session start) and nudge.py (the user's
message).

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "claims" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "recall" / "scripts"))

import claims  # noqa: E402
import nudge  # noqa: E402
import overview  # noqa: E402

CLAIMS = {
    "2026-10-08-linear-ramp-residual": dict(
        status="sealed",
        title="Simulated linear ramp leaves a 31.1 µm residual CoM oscillation",
        statement="With a linear 200 ms ramp the residual oscillation is 31.1 µm.",
        holds_when="Simulation (transport_sim); y_coil -5.5063 → -1.5318 A.",
        evidence="residual_um = 31.1\nramp = linear\n",
    ),
    "2026-10-10-sta-ramp-removes-com": dict(
        status="sealed",
        title="Simulated STA-type ramp removes the residual CoM oscillation",
        statement="An STA ramp reduces the residual from 31.1 µm to 0.009 µm.",
        holds_when="Simulation (transport_sim); noise-free drivers.",
        evidence="residual_um = 0.009\nramp = sta\nRuntimeWarning: overflow in exp\n",
    ),
    "2026-10-12-noise-budget": dict(
        status="draft",
        title="Current noise of 1e-5 heats the cloud by 3 nK/s",
        statement="Relative current noise 1e-5 gives a heating rate of 3 nK/s.",
        holds_when="Model; white noise up to 10 kHz.",
        evidence="heating_nK_per_s = 3.0\n",
    ),
}


def run(root: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = claims.main(["--root", str(root), *args])
    return code, out.getvalue(), err.getvalue()


def hook(module, event: dict) -> str:
    stdin, out = sys.stdin, io.StringIO()
    sys.stdin = io.StringIO(json.dumps(event))
    try:
        with contextlib.redirect_stdout(out):
            module.main()
    finally:
        sys.stdin = stdin
    return out.getvalue()


class LedgerFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.root = self.repo / "claims"
        for cid, c in CLAIMS.items():
            folder = self.root / cid / "evidence"
            folder.mkdir(parents=True)
            (folder / "02-output.txt").write_text(c["evidence"], encoding="utf-8")
            claim = {
                "id": cid,
                "status": c["status"],
                "title": c["title"],
                "statement": c["statement"],
                "holds_when": c["holds_when"],
                "claim_type": "result",
                "evidence": [{"kind": "output", "file": "evidence/02-output.txt"}],
                "citations": [],
            }
            (self.root / cid / "claim.json").write_text(json.dumps(claim), encoding="utf-8")
        review = self.root / "sources" / "arxiv-2502.09437" / "2026-10-09-eq-12.json"
        review.parent.mkdir(parents=True)
        review.write_text(json.dumps({
            "source": "arxiv:2502.09437", "locator": "Eq. (12)",
            "summary": "The shortcut-to-adiabaticity ramp shape holds.",
        }))

    def tearDown(self) -> None:
        self.tmp.cleanup()


class RecallTest(LedgerFixture):
    def test_the_claim_carrying_more_of_the_words_ranks_first(self) -> None:
        code, out, _ = run(self.root, "recall", "STA", "ramp", "residual")
        self.assertEqual(code, 0)
        first = out.splitlines()[0]
        self.assertTrue(first.startswith("2026-10-10-sta-ramp-removes-com"), out)
        self.assertIn("words found: 3 of 3", out)

    def test_an_ending_does_not_matter(self) -> None:
        _, out, _ = run(self.root, "recall", "oscillations")
        self.assertIn("2026-10-08-linear-ramp-residual", out)
        self.assertIn("2026-10-10-sta-ramp-removes-com", out)

    def test_a_number_is_found_with_either_sign_and_not_inside_another(self) -> None:
        _, out, _ = run(self.root, "recall", "5.5063")
        self.assertIn("2026-10-08-linear-ramp-residual", out)
        _, out, _ = run(self.root, "recall", "0.00")
        self.assertIn("no claim or source review carries", out)

    def test_drafts_are_found_and_marked_as_drafts(self) -> None:
        _, out, _ = run(self.root, "recall", "heating", "noise")
        self.assertIn("2026-10-12-noise-budget  [result, draft]", out)

    def test_evidence_files_are_searched(self) -> None:
        _, out, _ = run(self.root, "recall", "--exact", "overflow in exp")
        self.assertIn("2026-10-10-sta-ramp-removes-com", out)
        self.assertIn("evidence evidence/02-output.txt: RuntimeWarning", out)
        self.assertNotIn("2026-10-08", out)

    def test_exact_is_complete_and_unranked(self) -> None:
        _, out, _ = run(self.root, "recall", "--exact", "31.1")
        self.assertIn("2026-10-08-linear-ramp-residual", out)
        self.assertIn("2026-10-10-sta-ramp-removes-com", out)

    def test_source_reviews_are_searched_too(self) -> None:
        _, out, _ = run(self.root, "recall", "shortcut", "adiabaticity")
        self.assertIn("sources/arxiv-2502.09437/2026-10-09-eq-12.json  [source review]", out)

    def test_nothing_found_says_so(self) -> None:
        _, out, _ = run(self.root, "recall", "magnetometer")
        self.assertIn("no claim or source review carries any of: magnet", out)
        _, out, _ = run(self.root, "recall", "--exact", "magnetometer")
        self.assertIn("nothing in the ledger contains", out)

    def test_titles_are_every_claim_newest_first(self) -> None:
        _, out, _ = run(self.root, "recall", "--titles")
        ids = [line.split()[0] for line in out.splitlines()]
        self.assertEqual(ids, sorted(CLAIMS, reverse=True))

    def test_an_empty_query_is_refused(self) -> None:
        code, _, err = run(self.root, "recall")
        self.assertEqual(code, 2)
        self.assertIn("--titles", err)


class OverviewHookTest(LedgerFixture):
    def test_every_title_and_the_drafts_reach_the_agent(self) -> None:
        for i in range(60):  # no cap: a ledger of 63 claims is listed whole
            folder = self.root / f"2026-09-{i % 28 + 1:02d}-extra-{i}"
            folder.mkdir()
            (folder / "claim.json").write_text(json.dumps(
                {"id": folder.name, "status": "sealed", "title": f"Extra {i}"}
            ))
        out = json.loads(hook(overview, {"cwd": str(self.repo), "source": "startup"}))
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("holds 63 claim(s)", context)
        for cid in CLAIMS:
            self.assertIn(cid, context)
        self.assertIn("Extra 59", context)
        self.assertIn("Drafts not yet sealed (1; claims.py pending says why): 2026-10-12-noise-budget", context)

    def test_silent_without_a_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            self.assertEqual(hook(overview, {"cwd": other}), "")

    def test_silent_on_an_empty_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            (Path(other) / "claims").mkdir()
            self.assertEqual(hook(overview, {"cwd": other}), "")


class NudgeHookTest(LedgerFixture):
    def note(self, prompt: str) -> str:
        out = hook(nudge, {"cwd": str(self.repo), "prompt": prompt})
        return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""

    def test_questions_about_earlier_work(self) -> None:
        for prompt in (
            "Did we already test the STA ramp with noise?",
            "Have we ever tried dt = 0.005?",
            "Use the same cutoff as last time.",
            "Let's continue where we left off.",
        ):
            self.assertIn("asks whether something was done before", self.note(prompt), prompt)

    def test_contradictions(self) -> None:
        note = self.note("Doesn't this contradict the residual we found?")
        self.assertIn("contradicts earlier work", note)
        self.assertIn('"contradict"', note)

    def test_doubts(self) -> None:
        for prompt in (
            "I think you're hallucinating that number.",
            "Are you sure? You seem confused.",
            "Where does that number come from?",
        ):
            self.assertIn("doubts what you said", self.note(prompt), prompt)

    def test_an_ordinary_request_says_nothing(self) -> None:
        self.assertEqual(self.note("Plot the heating rate against the noise level."), "")

    def test_silent_without_a_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            self.assertEqual(hook(nudge, {"cwd": other, "prompt": "did we already?"}), "")


class HooksRegisteredTest(unittest.TestCase):
    def test_both_hooks_are_in_hooks_json_and_exist(self) -> None:
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
        for event, script in (("SessionStart", "overview.py"), ("UserPromptSubmit", "nudge.py")):
            command = hooks[event][0]["hooks"][0]["command"]
            self.assertIn(f"skills/recall/scripts/{script}", command)
            self.assertTrue((ROOT / "skills" / "recall" / "scripts" / script).is_file())

    def test_the_chat_bundle_includes_recall(self) -> None:
        bundle = (ROOT / "clients" / "chat" / "bundle.sh").read_text()
        self.assertIn(" recall ", bundle)
        self.assertTrue((ROOT / "skills" / "recall" / "references" / "chat.md").is_file())


if __name__ == "__main__":
    unittest.main()
