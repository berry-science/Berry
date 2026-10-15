# The labbook from a chat window

In a chat window — Claude.ai, ChatGPT — the labbook lives in the
[Berry Science Library](https://berry.science/library), next to the
claims. After each claim you add **one step**: why it was taken, what was
done, what it means, in the researcher's voice. berry.science adds the
rest — the claim's box, its figures, the papers it checked, the
conventions — and rebuilds the PDF in the background. The researcher
reads it on berry.science; you can hand them the link.

**A step is a claim.** Each step shows one published claim, and
`add_labbook_step` refuses a step without one. The labbook is not where
notes from the conversation, a summary or a chapter about a phase go:
those findings are claims, to be recorded first
(berry-research-monitoring-chat.md, "Documenting a phase"). A step's
`why`, `what` and `means` are a few sentences each — the claim's box
carries the substance.

What is not a finding goes, briefly, into:

- **where things stand**: three or four sentences;
- **the open points**: plans, questions, hypotheses;
- **the notes** — only what the researcher explicitly asks to have
  written down beyond the claims: context, decisions, remarks.
  `update_labbook` with `notes`; they print last, after the open points.
  `notes` replaces what is there, so read them with `get_labbook` and
  add to them. Write notes after the findings they touch are recorded as
  claims, never in place of one, and tell the researcher they are notes,
  not claims.

A new labbook (`create_labbook`) can be started before its first claim,
and where things stand and the open points set right away with
`update_labbook`.

You never read or rewrite the whole labbook. `get_labbook` gives you its
head — the voice, where things stand, the open points, the last two
steps — which is all you need for the next step. So the work per claim
stays the same however long the project gets.

## Which labbook

A labbook is one research project. Decide where a step goes in this
order, and stop at the first that answers:

1. **The claim's citations decide.** If the claim cites a claim that is
   already shown in a labbook (`get_claim` lists them under `labbooks`),
   the step goes there — no question. (Only if
   its citations point into different labbooks, ask.)
2. **This conversation already decided.** Keep using the labbook it used.
3. **One labbook, and the topic fits** its title and description: use it,
   and say so in one line at the end of your answer — *"Added to
   'Transport im Atomchip' — tell me if it belongs elsewhere."*
4. **Otherwise ask once** — for the first claim, in its setup message
   (berry-publish-claim-chat.md) — listing the labbooks (`list_my_labbooks`) and
   *"a new project"*. Do not wait for the answer: file the step without a
   labbook — it goes to the researcher's inbox — and move it with
   `move_labbook_step` when they answer.

A new project gets a labbook with `create_labbook`: a title, a sentence on
the question it pursues (that is what rule 3 checks against), the
researcher's language, and their voice.

**Create it where the project's claims are.** A step can show only a
claim every reader of the labbook can see, so the labbook lives in the
claims' space: claims shared in a team (`get_claim` shows `space_id` and
`shared`) → that team's `space_id`; claims in the researcher's private
library → private, the default; public claims → private or the team, as
the researcher wants. A labbook in another space refuses the step and
stays behind empty — there is no way yet to delete it.

## The voice

Before the first step, read the labbook's `voice`. If it is empty, write
it from the researcher's own messages in this conversation — the
language, the register, their words for the system and the quantities,
two or three sentences of theirs quoted — and set it with
`update_labbook`. Do not ask them to check it. Every step is then written in it:
their terms, not yours; no agent vocabulary (*claim ledger*, *evidence
item*) in the prose; plain and precise, no hedging, no praise.

## After every published claim

1. `get_labbook` — the head only.
2. `add_labbook_step` with the claim's id and:
   - `heading`: what the step found, in a few words;
   - `why`: the question it answered, and why it came next;
   - `what`: what was done, in plain words;
   - `means`: what it means for the question and the next step — a dead
     end said plainly;
   - `where_things_stand`: rewritten, three or four sentences;
   - `open_points`: the open points and follow-up questions as a list;
     an answered one moves into the step that answered it.

   You update where things stand and the open points yourself, without
   asking. When the researcher wants them changed, change them with
   `update_labbook`.
3. Mention it in one line at the end of your answer, with the labbook's
   `page_url` if they have not seen it yet. Never interrupt the researcher
   for it.

**Prose is Markdown**: paragraphs, `- ` lists, **bold**, *italic*,
`code`, inline math like `$\omega = 2\pi f$`, and `[[claim:<id>]]` to
refer to another claim. No raw LaTeX — anything else is printed as text.
Never copy the claim's statement or numbers into the prose beyond what a
sentence needs: the box shows the claim.

## Reading it

**The link for the researcher is `page_url`** — the labbook's page on
berry.science, which shows the PDF to them signed in, and to their team
if it is a team's. `render.pdf_url` is the API's address of the newest
PDF; it opens only with a token, so in a browser it reads as "no PDF has
been built yet". Never give it to a person.

`get_labbook` returns `render.status` and the build times. If the newest render failed, `render.error` says why —
usually something in a step's prose; fix it with a new step or
`update_labbook`. `render.source_url` is a zip of the LaTeX sources, for
the researcher who wants to compile or edit it elsewhere.
