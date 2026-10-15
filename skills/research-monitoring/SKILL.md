---
name: research-monitoring
description: Notice when a result has become a claim and have it drafted in the background, without interrupting the researcher. Use throughout a research session where Berry is enabled, when a [research-monitoring] note arrives, when deciding whether something is ready to record, and when the user asks to document or write up a phase or "the Berry documentation" — which means recording its claims.
---

# Research monitoring: notice findings, record them on the side

Research with an agent moves fast, and the moment a result becomes
something to build on passes without anyone writing it down. This skill is
the habit that catches that moment — and the rule that catching it never
costs the researcher their flow.

**In a chat window?** Follow [references/chat.md](references/chat.md)
instead: there is no hook and no background work there, only a one-line
offer at the end of an answer.

## How it runs

- **The hook tells you when to look.** With the `berry` plugin, a hook
  hands you a `[research-monitoring]` note when a command printed results
  or a run's output was read — a log, a data file, a background command's
  output — at most every ten minutes, with what was seen in between. A
  note nobody acted on comes back once with the user's next message.
  Without the plugin, look yourself after each run and each log you read.
- **No ledger yet?** Where Berry is enabled but `claims/` does not exist,
  offer once, at a natural moment, to start it with the first finding
  (`claims.py new` creates it). A missing ledger does not mean this skill
  does not apply.
- **You decide whether it is a claim**, with
  [references/claim-threshold.md](references/claim-threshold.md). Read it
  once per session.
- **A background agent drafts it.** If it is a claim, start a background
  agent with [references/claim-drafter.md](references/claim-drafter.md) as
  its instructions — in Claude Code the plugin's `berry:claim-drafter`, in
  Codex a subagent given that file — and carry on with what the researcher
  asked. Do not stop to ask them whether to record it. If your agent cannot
  run anything in the background, draft it yourself right after answering.

## When the note arrives

1. Judge it against the threshold. Most notes are not claims: a check, an
   intermediate print, a run that will be repeated with other parameters.
   Then ignore the note — say nothing about it.
2. If it is a claim, start the drafter **in the background** with
   everything it cannot find on its own, because it cannot see this
   conversation:
   - the finding in one or two sentences, with the numbers;
   - the command that was run, the commit (or that the code is
     uncommitted), and where the output is — a file, or the output pasted
     verbatim into the prompt;
   - what it builds on: earlier claims by id, papers with the passage used
     (and its source review, if one exists), data;
   - the conventions it is written in (`claims.py conv list`);
   - the conditions it holds under, as far as you know them.
3. If the result touches a claim whose title you know (skill `recall`),
   compare it with that claim — the number, the conditions. A result that
   disagrees with an earlier claim is said in the answer, with both,
   whether or not it becomes a claim.
4. Continue the researcher's task. At the end of your reply, one line:
   *"Drafted as claim `<id>` — have a look when you have a moment."*

The drafter writes the evidence, fills `claim.json`, runs `claims.py
check`, and stops. **It never seals.** Sealing is the researcher agreeing
to the claim, and happens when they have looked.

## Drafts waiting

- `claims.py pending` lists the drafts not yet sealed, with what `check`
  says about each. With the plugin, when drafts have waited more than an
  hour, the user's next message brings a one-line `[research-monitoring]`
  note listing them — once per session.
- **Before the next step builds on a draft**, it has to be agreed and
  sealed (a sealed claim may only rest on sealed claims). That is the one
  moment to bring it up mid-task — in a sentence, with the claim's title
  and statement: *"The next step uses the residual from draft `<id>`;
  shall I seal it?"*
- At a natural pause (the researcher asks what is open, a task is done),
  offer to go through the waiting drafts together.

## Documenting a phase

When the researcher asks to document, write up or record a phase, a day's
work or "the Berry documentation", the job is the claims. The labbook
follows from them; it never replaces them.

1. **List the findings.** Go back through the phase — the runs, their
   output, the commits, the conversation — and list each result that meets
   the threshold, one line each, in the order it was made. Negative
   results and calibrations count. Drafts already waiting
   (`claims.py pending`) are on the list.
2. **For each, what it rests on**: which of the others it uses — a value,
   a setting, a calibration, a conclusion — which earlier claims (skill
   `recall`), which papers. In a phase that built step by step, most
   findings use an earlier one. One that uses nothing gets a sentence
   saying why.
3. **For each, its evidence**: the output verbatim, on disk or in the
   conversation, and the commit. If the output is gone, rerun it, or ask.
   Otherwise that finding is not recorded; say so. Never rebuild evidence
   from a summary.
4. **Show the list** — finding, rests on, evidence there or missing — and
   ask which to record. This is the one question.
5. **Record them from the bottom up**: first the ones that rest on nothing
   in the list, then each later one, citing the earlier ones (`local`).
   Hand each drafter the ids it cites; drafts are sealed in the same
   order, a cited one first.
6. **The labbook**: one step per sealed claim (skill `labbook`).
7. **Anything else they asked to have written down** that is not a
   finding — context, decisions, remarks — goes into the labbook's notes,
   at the end, after the claims. Say that these are notes, not claims.

If nothing in the phase reaches claim level, say so. Never write prose in
its place.

## When a paper comes in

When the work starts to take a value, an equation or a method from a paper,
that passage is checked before a claim rests on it (skill `review-source`).
It can run in the background too (the review-source skill's
`references/source-reviewer.md`; in Claude Code `berry:source-reviewer`); the claim that
uses it waits for the verdict before it is sealed.

## Rules

- **Never interrupt for bookkeeping.** The researcher's question comes
  first; recording happens beside it. The only exception is above: a draft
  something is about to rest on.
- **Never seal without the researcher.** Unless they said, for this
  session, to record findings without stopping.
- **One finding per claim.** If a run settles two things, draft two claims.
- **Negative results count.** A method that did not work, with its
  conditions, is a claim.
- **Nothing leaves the machine.** Drafting is local; publishing is a
  separate step, only when asked (skill `publish-claim`).
