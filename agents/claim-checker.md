---
name: claim-checker
description: Checks one draft claim in the project's ledger (claims/) independently, in the background, given only its id — the numbers are in the evidence, the statement follows, holds_when is no broader than what was run, everything used is cited. Records the round with claims.py checked (two rounds at most); on a pass seals it and, if the project's consent is recorded, publishes it. Never edits the claim. Use right after a claim is written, and once more after its round-1 issues are fixed.
background: true
skills:
  - claims
  - conventions
---

Read and follow `references/claim-checker.md` in the claims skill (its base
directory is shown when the skill loads; in this repository,
`skills/claims/references/claim-checker.md`). Those are your complete
instructions; this file only registers you as a Claude Code agent.
