---
name: check-claims
description: Check recorded claims one at a time — every number in its evidence, the statement following from it, every step cited — and the chain they form, in the project's ledger (claims/) or, from a chat window, in the Berry Science Library. Use when the user asks to check, audit or verify findings, before publishing, and before relying on an older claim.
---

# Check recorded claims

**In a chat window?** If you are not running inside the user's research
repository, the claims to check are in the Berry Science Library, not in a
ledger: follow [references/chat.md](references/chat.md) instead.

Each claim in the ledger (skill `record-claim`) is small enough to be
checked on its own: one statement, the evidence behind it, and citations to
what it rests on. Checking a result means checking it claim by claim, down
the chain it rests on.

The script is the one `record-claim` uses:

```bash
python3 <base directory of the record-claim skill>/scripts/claims.py <command>
```

It is in `../record-claim/scripts/` from this skill's base directory. The
format is in `../record-claim/references/claim-format.md`.

## Decide the scope

- **One result:** `claims.py trace <id>` lists everything it rests on. Check
  those claims, from the bottom of the tree up.
- **The whole ledger:** every sealed claim. Say how many there are before
  starting a long check.
- **Before publishing:** the claim and every unpublished claim it cites
  (`claims.py order <id>`).

**Then leave out what was already checked.** A sealed claim does not
change, so an audit of it holds until something it rests on does.
`claims.py audit-status [ids…]` lists, of the claims in scope, only those
that need you:

- `never` — never audited: steps 2 and 3 in full.
- `STALE` — audited, but something changed since, and it says what: a claim
  below it was re-sealed, a review of a paper it uses changed, a new claim
  refutes it or something below it, or a new review of a paper it uses
  found a passage wrong. If the claim itself is unchanged — the usual case
  — its own judgment (step 2) still stands: redo only step 3, the chain,
  against what changed, and record it with `--scope chain`.
- Claims not listed are `current`: say they were audited before and are
  unchanged, and do not read them again — unless the user asks for a fresh
  audit.

Drafts are never audited: they still change. Check them, but record
nothing.

## 1. The mechanical check

`claims.py check [ids…]`. Errors mean the record itself is broken: a missing
file, a citation to nothing, a sealed claim that changed (or a convention or
source review it relies on that changed), a convention that is not defined,
a claim that uses a paper's passage its review found wrong. Report them
first; they are facts, not judgments. Warnings are leads for step 2.
Without ids, `check` also checks `conventions.json` and every source review
in `sources/`.

## 2. Each claim on its own

Read the claim's `claim.json` and **every** evidence file. Then answer, for
this claim alone:

1. **Is each number in the statement in the evidence?** Find it — in the
   output, the data, the figure's inline data, the derivation. A number
   that is only in the reasoning is not evidenced. Rounding must be right.
2. **Does the statement follow?** From the reasoning and the material
   together. Look for a step that does not follow, a comparison against
   something not shown, a conclusion stronger than the evidence (one run
   stated as a general rule, a simulation stated as a measurement).
3. **Does `holds_when` match the evidence?** Parameter ranges, system,
   versions: is the claim stated more broadly than what was run?
4. **Is every step it takes cited?** A value, method or result the claim
   uses must be in its citations: an earlier claim, a paper, the data, the
   commit. Something used but not cited is a gap — name what is missing.
   Look for it: a value or result in the reasoning that is in neither this
   claim's evidence nor a cited claim; a claim that cites no earlier
   claim although earlier claims on the same subject came before it
   (`claims.py check` asks both of drafts).
5. **Do the citations say what they are used for?** For a `local` citation,
   open the cited claim: does it state what this claim takes from it, under
   compatible conditions? For an outside citation, judge from what you can
   see; say when you could not check it.
6. **Is the code traceable?** A full commit hash, reachable from a remote,
   and the command that was run. `check` already looked; repeat only if it
   warned.
7. **Are the numbers in the conventions the claim names?** Read the named
   versions (`claims.py conv show <key>`). A factor 2, 2π or a sign that
   only works under another convention is a finding. A value taken from a
   paper must be converted to the project's conventions, with the
   conversion shown in the reasoning.
8. **Was the paper's passage checked?** For each paper the claim `uses`:
   is there a `locator` and a source review (skill `review-source`)? Read
   the review: does its verdict, and its mapping of conventions, support
   the way this claim uses the passage? If the passage was corrected, does
   the claim build on the correction?
9. **Does the derivation's check say what the claim says?** For a
   `derivation` with a check script (skill formalize-derivation), read its
   output. Compare each step *as written* with the step *as checked*: the
   check proves the second. Hold the statement to the verdicts — a step
   that is `limit-only`, `dims-only`, `inconclusive` or `unchecked`
   supports less than "derived"; an approximation left `unchecked` is a
   gap. Look at the mutants that survived. An output captioned
   `As written:` with a FAIL records an error the check found in the
   original derivation: does the reasoning say so, and does the claim
   rest on the corrected run?

Do not judge whether the finding is interesting, novel or well written.

## 3. The chain

After the claims one by one: does the top result still hold given what you
found below it? A refuted or weak claim at the bottom weakens everything
that `uses` it — say which claims depend on it (`trace` from the top shows
the path).

## Reporting

For each claim with findings, write:

- the claim id and title;
- each finding: what is wrong, **quoting** the exact text from the claim or
  the evidence file (and naming the file), why it is wrong, and how much it
  matters — `minor` (wording, rounding with no effect), `moderate` (a gap
  or overstatement that a reader would have to resolve), `major` (the
  statement does not follow, or a number is wrong);
- for a gap, what would close it: a citation, a run, a narrower statement.

Then list the claims with no findings, by id, so it is clear they were read.
Say plainly when the ledger holds up: no findings is a good result. A false
alarm costs as much as a miss.

Put the report in the conversation. Write it to a file only if the user
asks — not inside a claim's folder.

## Record the audit

For every sealed claim you checked, record what you found, so the next
check can skip it:

```bash
claims.py audit <id> --clean --agent "<you, with your exact model id>"
claims.py audit <id> --findings findings.json --agent "…" [--human "…"] [--scope chain]
```

`findings.json` is a list, one entry per finding: `{"severity": "minor" |
"moderate" | "major", "text": "what is wrong and why", "quote": "the exact
text", "file": "evidence/02-output.txt"}`. Write it outside the ledger (or
delete it afterward); the audit copies it into `claims/audits/<id>.json`,
which is committed with the ledger. `--human` names a person who went
through the audit with you, if one did.

An audit records the claim's seal and the state of everything below it, so
`audit-status` can tell later whether it still holds. Findings do not
change the claim: a fix is still a new claim.

## Rules

- **Never edit a sealed claim**, even to fix what you found. A fix is a new
  claim that cites the old one (`refutes` or `extends`), recorded with
  `record-claim` once the user agrees.
- **Drafts may be fixed**, with the user's go-ahead.
- **Check against the files, not your memory** of the session that wrote
  them. The point is that the record stands on its own.
