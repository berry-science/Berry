"""claims.py check: a claim names the agent that did the work, with its model id.

    python3 -m unittest discover -s tests

Standard library only, like claims.py.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "record-claim" / "scripts"))

import claims  # noqa: E402

WARNING = "no contributor names the agent with its model id"


class ContributorsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "claims"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            claims.main(["--root", str(self.root), "new", "A finding", "--type", "result"])
        self.cid = out.getvalue().splitlines()[0]
        folder = self.root / self.cid
        (folder / "evidence" / "01-reasoning.md").write_text("Why it holds.\n")
        self.claim = json.loads((folder / "claim.json").read_text())
        self.claim.update(statement="It holds.", holds_when="Model.", provenance={"uncommitted": True})

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def warned(self, **fields) -> bool:
        claim = dict(self.claim, **fields)
        (self.root / self.cid / "claim.json").write_text(json.dumps(claim))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            claims.main(["--root", str(self.root), "check", self.cid])
        return WARNING in out.getvalue()

    def test_a_product_name_alone_is_not_enough(self) -> None:
        self.assertTrue(self.warned(contributors=["Claude Code", "SymPy 1.14.0"]))
        self.assertTrue(self.warned(contributors=[]))

    def test_a_model_id_in_contributors_or_provenance(self) -> None:
        self.assertFalse(self.warned(contributors=["Claude Code (claude-opus-5-5)", "SymPy 1.14.0"]))
        self.assertFalse(self.warned(contributors=["Codex (gpt-5.1)"]))
        self.assertFalse(self.warned(contributors=["Claude Code"],
                                     provenance={"uncommitted": True, "agent": "Claude Code (claude-sonnet-5-5)"}))


if __name__ == "__main__":
    unittest.main()
