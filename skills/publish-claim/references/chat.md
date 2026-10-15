# Publish claims from a chat window

Use this when you are **not running inside the user's research
repository**: a chat window such as Claude.ai or ChatGPT, where you cannot
run commands on the user's machine or read their files. The researcher
works the usual way — you propose code, they run it on their own machine
or server, and they paste the results back — and each finding is published
straight to the [Berry Science Library](https://berry.science/library).
There is no local ledger: the Library is the record, and its claims cannot
be edited either.

What is weaker than in a repository: there is no commit hash. The link
between a number and the code that produced it rests on the code being
attached in full and on the user confirming it ran unchanged. Say so in the
claim; never hide it.

## Before you start

You need the Berry Science connector (MCP server
`https://api.berry.science/mcp`) with its `publish_claim` tool. If it is not
available, tell the user to add it as a custom connector with that URL and
OAuth sign-in, with their berry.science account, then stop. Never publish a
claim anywhere else instead.

## When to offer it

When a result settles something — a number computed, a method shown to
work, a calibration, an approach shown not to work — offer to record it as
a claim, in one line. Negative results are findings. Record a result
before the next step builds on it. Do not offer for plans, intentions, or
summaries of what others found.

## The first claim: one setup message

When the researcher has no claims yet, put what a project asks only once
into **one message** with the first draft: the conventions its numbers
depend on, read from the code and their messages
(berry-conventions-chat.md) — confirm or correct; and the labbook's title
(the project's question, in a few words) and language
(berry-labbook-chat.md). One reply settles it; a proposed title and
language stand if they do not answer. The voice is not asked.

## Gather the evidence

Everything in a claim comes from this conversation, and every result from
what the user pasted:

1. **The output, verbatim.** Ask for the full output of the run if what you
   have is only part of it. Copy it exactly; never retype, shorten or
   reconstruct it.
2. **The code as it ran.** Show the code you have and ask: *"Did you run
   exactly this, unchanged?"* If they changed anything, ask them to paste
   the version they ran. Attach that version in full.
3. **The parameters**, and the environment if the user knows it (machine,
   language and library versions). Ask once; do not insist.
4. **What it builds on.** Earlier claims, by their Library id — from this
   conversation, or found as berry-recall-chat.md describes (`search`,
   `find_literal` for its key numbers) — and papers,
   datasets and methods, by DOI, arXiv id or URL. For a paper the claim
   takes a value or an equation from: the passage (`locator`), and its
   source review — look it up with `get_source`, and if nobody checked
   it, check it first (berry-review-source-chat.md).
   Write it down as one line for the draft — *Builds on: …* — or, if it
   builds on no earlier claim, one sentence saying why. A finding from a
   project that has earlier claims rarely builds on none.
5. **The conventions** its numbers are written in: `list_my_conventions`
   for the researcher's, and berry-conventions-chat.md when there are none
   yet. A value from a paper is converted to them first, and the reasoning
   shows the conversion.

**Push back when the evidence is not there.** If the output a claim rests
on is not in this conversation — only a summary, a recollection, a number
mentioned in passing — do not draft it: ask the researcher to paste the
output, or to rerun. If it uses the result of an earlier finding that is
not recorded, record that one first. Say it in a sentence or two; a claim
without its evidence costs more than a claim not recorded.

**Your own knowledge is never evidence.** What you know about the system
may go into the reasoning, as a cited source, or into `holds_when` as a
stated assumption — never as a result. A number in the claim that is not
in pasted material is a mistake.

## Check it yourself — this is the check

Publishing is final, and later claims will trust this one without
checking it again (berry-check-claims-chat.md). So the full check happens
now, once, before the researcher sees the draft. Answer each, and fix the
draft until every answer is yes:

1. **Is every number in the statement in the pasted material** — the
   output, the data, a figure's inline data — with the rounding right? A
   number only in the reasoning is not evidenced.
2. **Does the statement follow** from the reasoning and the material, with
   no step missing and nothing stronger than what was run?
3. **Does `holds_when` match what was run**: system, ranges, versions? One
   run is not a general rule; a simulation is not a measurement.
4. **Is everything it uses cited**, each earlier claim, paper and dataset,
   with what is taken from it? Go through the reasoning: every value,
   setting or result in it comes from this claim's own evidence or from a
   citation. A paper's passage: checked, with its source review?
5. **Are the numbers in the stated conventions**, and is a value from a
   paper converted to them?
6. **Does the code compute what the statement reports**, and did it run
   unchanged?

**Then run `check_claim_draft`** with the draft's title, statement,
`holds_when`, evidence and citations. It publishes nothing. It returns
the numbers in the statement that are in no evidence item — fix those —
and the researcher's earlier claims closest to the draft that it does not
cite. For each of those: if the draft uses anything from it, cite it; if
not, you can say why. If the connector has no `check_claim_draft`, do the
same with `search` on the title and statement.

Tell the researcher in one line what you checked, and anything you could
not. Then, if you have a Python tool, use it too:

- Every number in the statement appears in the pasted output or data.
- Each evidence item is at most 16 000 characters.
- The code's git blob hash, so that if this exact file is committed later,
  `git log --find-object=<hash>` finds the commit. Hash the code exactly as
  it ran, as UTF-8 with `\n` line endings and its final newline:

  ```python
  import hashlib
  data = code.encode("utf-8")
  print(hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest())
  ```

  Add it as the anchor `git-blob:<hash>`. Without a Python tool, leave it
  out — never write a hash you did not compute.

## What the claim carries

The `publish_claim` tool describes its fields; what it cannot know:

- `evidence` in reading order: `reasoning` first (markdown, citing
  references as [1], [2]), then the `output` verbatim, the `code` (one
  item per file, with `language`), `parameters` as JSON, and a `figure`
  as a Vega-Lite spec with its data inline where useful. An item over
  16 000 characters: attach the part the statement rests on and say in
  its caption that it is an excerpt, and of what.
- `holds_when` starts with the kind of evidence (simulation, model,
  measurement), then the system, ranges, versions, what was held fixed,
  and any assumption you added.
- `conventions`: each statement in full, exactly as before for the same
  key and version.
- `contributors`: yourself first, with your model's exact name as you know
  it — never a guess — then the tools.
- `anchors`: `git-blob:<hash>` only if you computed it.
- `provenance`: `{"uncommitted": true, "code_source": "proposed in a
  <Claude.ai/ChatGPT> conversation and run by the user", "ran_unchanged":
  true}` (or `false`, with the user's version attached), plus the machine
  and versions if known.
- `private`: **`true`**, unless the user said otherwise for this claim.

## Writing the claim

- **One finding per claim.** Two findings are two claims; the second cites
  the first.
- **No hedging**, and no judgment without its reference point: not
  *negligible* or *dominant*, but the comparison, with what it is compared
  against named and from the same work.
- **State it as narrowly as it was run.** One run is not a general rule; a
  simulation is not a measurement.

## Several claims at once

When a batch is recorded — documenting a phase
(berry-research-monitoring-chat.md) — confirm the batch, not each claim:

1. Draft them all, in order, and run each one's check.
2. Show them in **one message**, numbered: per claim the title, statement,
   *Builds on* line and evidence list, in a few lines. Then two questions,
   once: *"Was all the code run as shown?"* and *"Publish these privately?
   Name any to leave out."*
3. On their go-ahead, publish them in order — each one's citations of the
   others use the ids just given — and add each one's labbook step.
4. Reply with the list of ids and links.

A claim whose code was changed before it ran, or that they leave out, is
not published; say which.

## Show it, then publish

1. Show the user the title, statement, `holds_when`, the *Builds on* line
   and the citations, the list of evidence items, and that it will be
   private. Uploads are permanent:
   there is no edit and no delete. Wait for their go-ahead.
2. Call `publish_claim`.
3. Check the reply's `visibility`. It must be `"private"` unless the user
   asked otherwise; if not, stop and ask them to check the claim on
   berry.science.
4. Give the user the claim's id and link,
   `https://berry.science/library/<id>`, and keep the id in mind: later
   claims in this conversation that build on it cite it by that id.
5. Add its step to the project's labbook (berry-labbook-chat.md):
   `add_labbook_step` with the claim's id — only the step's prose, in the
   researcher's voice. One line about it at the end of your answer.

## Rules

- **A wrong claim is never edited** (it cannot be). Publish a new claim that
  cites it with relation `refutes`, saying what was wrong.
- **Never publish without the user's go-ahead** for that claim, in this
  conversation — given for it alone, or for a list that showed it.
- **Never publish a claim anywhere but the Berry Science connector.**
