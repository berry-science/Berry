---
name: claims
description: Record research findings as checkable claims in the project's ledger (claims/), have each checked independently, and publish them to the Berry Science Library once the project has consented. Use when a result, method, calibration or dead end is established, when a [claims] note arrives, when the researcher asks to record, document, write up or publish findings (a phase, a day's work, "the Berry documentation"), and when a project records its first claim.
---

# Claims

**In a chat window** (Claude.ai, ChatGPT: no shell in the research
repository)? Follow [references/chat.md](references/chat.md) instead.

A **claim** is one finding: a statement that could be false, the conditions
it holds under, and the evidence behind it, citing what it builds on. The
ledger is `claims/` in the research repository, committed with the code,
kept by one script (`claims.py -h` for the rest). In a repository that holds
several projects, each keeps its own: run `claims.py init` once in the
project's folder before its first claim, or that claim lands at the top.

```bash
python3 <this skill's base directory>/scripts/claims.py <command>
```

## Notice

A hook hands you a `[claims]` note when a run printed results or its output
was read; without the hook, look after each run. Judge it against
[references/claim-threshold.md](references/claim-threshold.md). Most results
are not claims: then say nothing. A result that disagrees with a claim you
know (skill `recall`) is said in your answer, with both.

## Write

Write the claim yourself, right away, then carry on with the researcher's task.

1. **Evidence first.** Every number comes from one run of one version of the
   code: commit the files that run used, only those; if the code changed
   since, rerun. If the output is gone, rerun it or say it cannot be recorded.
2. `claims.py new "<title>" --type result` (or `method`, `negative_result`,
   `calibration`; `--date` for a finding made earlier) starts
   `claims/<id>/claim.md`. Fill it as in
   [references/claim-format.md](references/claim-format.md): the reasoning in
   the words you would use anyway, evidence as **paths to files already on
   disk**, and citations — earlier claims (`claims.py recall`, not memory),
   the commit, papers. A value taken from a paper needs a source review of
   that passage first (skill `review-source`, `berry:source-reviewer` in the
   background). Numbers are in the project's conventions (skill
   `conventions`). Contributors: you first, with your exact model id.
3. `claims.py check <id>` until there are no errors; answer each warning.

One finding per claim. The title is the finding, not the topic; the
statement carries the numbers and names what it compares against;
`holds_when` starts with the kind of evidence (simulation, model,
measurement). No session labels (*round 5*, *run B*) and no plans.

## Check

Start the `claim-checker` agent in the background with only the claim id
(Claude Code: `berry:claim-checker`; elsewhere a subagent given
`references/claim-checker.md`). It reads files, never this conversation, and
records its verdict with `claims.py checked`. Never check your own claim.

- **Pass:** it seals and, with the project's consent, publishes. You get one
  line; start the labbook step in the background (`berry:labbook-writer`,
  skill `labbook`).
- **Issues:** at a natural pause, fix them in `claim.md` — or give the
  reason for leaving one in the claim itself, where the checker reads it —
  and start the checker once more. That is the last round.
- **Issues again:** the claim is **held**, a draft never published.
  `claims.py pending` lists it with its open issues for the researcher.

A sealed claim cites only sealed claims: check the ones it cites first.
After sealing, `claims.py index`; commit `claims/` with your next commit.
`claims.py trace <id>` shows what a claim rests on; skill `check-claims`
audits sealed ones.

## Publish

`claims.py publish <id>` (or `--ready`) sends sealed claims, with what they
rest on, to the place `claims.py where` records, and verifies each by
reading it back. Private by default; only the researcher makes a claim
public, on berry.science. **Consent is asked once per project, never per
claim**: `claims.py where --consent yes|no`, with `--space <id>` for a team
and `--labbook <id>`. `claims.py login` once per machine. Without consent,
nothing leaves the machine.

## The first claim of a project

Ask everything a project needs once in **one message**, beside the first
claim, and carry on without waiting:

- may sealed claims go to berry.science, and where: their private library,
  or a team and its labbook (`claims.py where` lists both once signed in);
  and may you push the commits claims cite;
- the conventions its numbers depend on, as read from the code (skill
  `conventions`): confirm or correct;
- the line `check` gives for `.gitignore`, if git ignores an evidence file
  (for a project below the top it names the ledger's path, `!sub/claims/**`).

Until they answer, claims are checked and sealed, not published.

## Documenting a phase

When asked to document or write up a phase, the job is its claims, never
prose. List each finding that meets the threshold, with what it rests on
and whether its output still exists; record them bottom up — first those
resting on none of the others, then each citing the earlier ones — and
check each. Say which could not be recorded for lack of evidence. What else
they want written down goes into the labbook's notes, as notes.

## Rules

- **Sealed claims are never edited.** A wrong one is answered by a new claim
  that `refutes` it; a refinement `extends` it.
- **Evidence is the output**, copied from disk by `claims.py`, never retyped
  or rebuilt from memory. Every number in a claim traces to it.
- **Never interrupt for bookkeeping**: the researcher is asked only the setup
  message and about held claims.
