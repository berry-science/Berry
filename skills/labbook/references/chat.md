# The labbook from a chat window

In a chat window the labbook lives on berry.science, next to the claims.
After each published claim you add **one step** — why it was taken, what was
done, what it means, in the researcher's voice — and berry.science adds the
rest (the claim's box, figures, papers checked, conventions) and rebuilds the
PDF.

## Rules

- **A step is a claim.** `add_labbook_step` takes the published claim's id
  and refuses a step without one. A request to document or write up a phase
  means claims first (berry-claims-chat.md), then a step for each.
- **Notes** (`update_labbook` with `notes`) only for what the researcher asks
  to have written down beyond the claims, after those findings are claims.
  `notes` replaces what is there: read them with `get_labbook` and add.
  Tell the researcher these are notes, not claims.
- **The prose is short** — a few sentences per field; the box carries the
  claim. Never copy its statement or numbers beyond what a sentence needs.
  Markdown with inline `$…$` math and `[[claim:<id>]]`; no raw LaTeX.
- **Their voice.** The labbook's `voice`; if empty, write it from the
  researcher's own messages (language, register, their words, two or three
  sentences of theirs quoted) and set it with `update_labbook`, without asking
  them to check. Their terms, no agent vocabulary, no hedging, no praise.

## Which labbook

Stop at the first that answers:

1. The claim cites a claim already in a labbook (`get_claim` lists its
   `labbooks`): that one. Citations into different labbooks: ask.
2. This conversation already used one: that one.
3. One labbook (`list_my_labbooks`) whose title and description fit: use it,
   and say so in a line — *"Added to 'Transport in the trap' — tell me if it
   belongs elsewhere."*
4. Otherwise ask once (in the first claim's setup message, berry-claims-chat.md),
   listing the labbooks and *"a new project"*. Meanwhile add the step with no
   `labbook_id` — it waits in the inbox — and `move_labbook_step` it when they
   answer.

A new project: `create_labbook` with a title, a sentence on its question
(what rule 3 checks against), the researcher's language and voice — **in the
claims' space** (team claims → that team's `space_id`; private claims →
private, the default). A step can show only a claim every reader of the
labbook can see; a labbook in the wrong space refuses it and cannot be
deleted yet.

## After every published claim

1. `get_labbook` — the head only (voice, where things stand, open points,
   the last two steps); never the whole book.
2. `add_labbook_step` with `claim_id`, `labbook_id`, `heading` (what the step
   found), `why`, `what`, `means`, and the rewritten `where_things_stand` and
   `open_points` (an answered point moves into the step that answered it).
3. One line at the end of your answer, with the labbook's `page_url` the
   first time. Never interrupt the researcher for it.

## Reading it

Give the researcher `page_url` — never `render.pdf_url`, which opens only
with a token. `get_labbook` shows `render.status`; a failed render's
`render.error` usually points at a step's prose; steps are never edited, so
fix it in the next step or with `update_labbook`, and tell the researcher.
`render.source_url` is a zip of the LaTeX sources.
