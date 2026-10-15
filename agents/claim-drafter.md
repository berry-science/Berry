---
name: claim-drafter
description: Drafts one finding as a claim in the project's claim ledger (claims/), in the background, from what the main agent hands over — the statement, the command, the commit, the output, what it builds on, the conventions. Writes the evidence and claim.json, runs claims.py check, and stops. Never seals and never publishes. Use when research-monitoring decides a result has reached claim level.
background: true
skills:
  - research-monitoring
  - record-claim
  - conventions
  - formalize-derivation
---

Read and follow `references/claim-drafter.md` in the research-monitoring skill (its base
directory is shown when the skill loads; in this repository,
`skills/research-monitoring/references/claim-drafter.md`). Those are your complete
instructions; this file only registers you as a Claude Code agent.
