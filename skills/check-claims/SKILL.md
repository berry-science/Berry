---
name: check-claims
description: Audit sealed claims in the project's ledger (claims/) when the researcher asks — the whole ledger, a result and everything it rests on, or an older claim before relying on it — or, from a chat window, claims in the Berry Science Library. Checks each claim against its evidence and the chain they form, and records the audit. Not for new drafts: those get the claim checker (berry:claim-checker) automatically.
---

# Audit recorded claims

**In a chat window?** If you are not inside the researcher's repository, the claims are in the
Berry Science Library: follow [references/chat.md](references/chat.md) instead.

Every new claim is checked once, before it is sealed, by the claim checker. This skill is the
audit the researcher asks for later: of the whole ledger, of a result and everything below it,
or of an older claim before new work rests on it. The script is
`../claims/scripts/claims.py` from this skill's base directory.

## Scope

- **One result:** `claims.py trace <id>` lists everything it rests on; audit from the bottom up.
- **The whole ledger:** every sealed claim. Say how many before starting a long audit.

Then leave out what was audited already: `claims.py audit-status [ids…]` lists only the claims
that need you. `never`: audit it in full. `STALE`: something below it changed, and it says
what; the claim itself is sealed, so its own judgment stands — redo only the chain against what
changed, and record with `--scope chain`. Claims not listed are current: say so, don't re-read
them unless the researcher asks for a fresh audit. Drafts are not audited (they still change);
look at them if asked, record nothing.

## The audit

1. `claims.py check [ids…]`. Errors are facts — a missing file, a citation to nothing, a sealed
   claim (or a convention or source review it relies on) that changed. Report them first;
   warnings are leads.
2. Each claim on its own: the same judgment the claim checker makes —
   `../claims/references/claim-checker.md`, its "Read" and "Judge" parts. The same standard:
   only what you can show from the files, a false alarm costs as much as a miss.
3. The chain: does the top result still hold given what you found below it? A refuted or weak
   claim weakens everything that `uses` it — say which (`trace` shows the path).

## Report and record

In the conversation (a file only if asked, never inside a claim's folder): for each claim with
findings, its id and title, and each finding with severity, the quoted text, its file, why it
is wrong, and what would fix it. Then the claims with no findings, by id, so it is clear they
were read. No findings is a good result — say so plainly.

Record every sealed claim you audited, so the next audit can skip it:

```bash
claims.py audit <id> --clean --agent "<you, with your exact model id>"
claims.py audit <id> --findings findings.json --agent "…" [--human "…"] [--scope chain]
```

`findings.json` is the list the checker uses: `{"severity": "minor" | "moderate" | "major",
"text", "quote", "file"}`. Write it outside the ledger; the audit copies it into
`claims/audits/<id>.json`, committed with the ledger. `--human` names a person who went through
the audit with you.

## Rules

- **Never edit a sealed claim**, even to fix what you found. A fix is a new claim citing the old
  one (`refutes` or `extends`), written once the researcher agrees.
- **Audit the files, not your memory** of the session that wrote them.
