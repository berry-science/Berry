# Claims in a chat window

For Claude.ai, ChatGPT and similar: no shell, no ledger, no background
agent. The researcher runs code elsewhere and pastes results back; each
finding is published to the [Berry Science Library](https://berry.science/library)
through the Berry Science connector (`https://api.berry.science/mcp`), and
nothing there is ever edited. Without the connector's `publish_claim`, tell
the researcher to add it and stop — never publish anywhere else.

## Once per conversation

- `list_my_claim_titles`, once, at the start of a conversation about the
  research: what is already established.
- **Ask once where claims go and whether to publish as you go** — unless
  the project's instructions say. The place: the private library, or a team
  (`list_my_spaces`) and one of its labbooks (`list_my_labbooks`;
  `create_labbook` for a new topic). Private unless they asked for public.
  With their yes, publish each finding as it is established, without asking
  per claim; without it, show each draft and publish on their go-ahead.
- With the first claim, the conventions its numbers depend on
  (`list_my_conventions`; berry-conventions-chat.md if there are none).

## When a result is a claim

After each pasted result or computation done here, judge it (as a skill:
`references/claim-threshold.md`): it could be false, with the numbers that
make it checkable; its output is in this conversation; its conditions can
be named; the next step builds on it. Negative results and calibrations
count; a run about to be repeated, a check, a plan do not. Most results are
not claims — then say nothing. One that disagrees with an earlier claim is
said, with both, either way. Answer the question first; a claim never
delays the answer.

## Draft

- **Evidence is what the user pasted, verbatim**: the output as printed,
  the code as it ran (ask once: *"Ran exactly this?"* — if not, paste their
  version), the parameters. Output not here — a summary, a number in
  passing: ask them to paste it or rerun; never rebuild it. Your own
  knowledge is never evidence — at most a cited source or an assumption
  in `holds_when`.
- **One finding per claim**, stated as narrowly as it was run. No hedging;
  a comparison names what it is compared against.
- `evidence`: `reasoning` first (citations as [1], [2]), then `output`,
  `code` (with `language`), `parameters`, a `figure` (Vega-Lite, data
  inline) where useful. Over 16 000 characters: the part the statement
  rests on, captioned as an excerpt.
- **Cite what it uses**: earlier claims by id (`search`, `find_literal` for
  its key numbers); papers by DOI or arXiv id with the `locator`. A value or
  equation from a paper only once its passage is checked (`get_source`,
  else berry-review-source-chat.md), citing the `source_review_id`.
- `holds_when` starts with the kind of evidence (simulation, model,
  measurement). `contributors`: yourself first, your exact model name, then
  the tools. `provenance`: `{"uncommitted": true, "code_source": "proposed
  in a chat, run by the user", "ran_unchanged": true, "check": "author's
  re-read in the same chat"}`. With a code tool, the anchor
  `git-blob:<sha1 of b"blob <len>\0" + the code as UTF-8>`; never a hash
  you did not compute.

## Check, then publish

1. `check_claim_draft`: fix each number it finds in no evidence item; cite
   each earlier claim it lists that the draft uses.
2. **The independent check, a separate pass.** Re-read the draft as a
   reviewer who sees only its fields and evidence, not the conversation:
   every number in the statement in the evidence, rounding right? Does the
   statement follow? `holds_when` no broader than what was run? Everything
   used cited, in the stated conventions? Fix, and re-read once more at
   most. Still an issue: do not publish; say in one line what is open.
   This is weaker than a coding agent's background checker — same model,
   conversation in mind — so read it as someone else's work.
3. `publish_claim` with the agreed `labbook_id` (it files the claim in that
   topic, where the labbook is); `private` / `space_id` only to override.
   The reply's visibility must be what was agreed; if not, stop and say so.
4. One line: what was published, with `https://berry.science/library/<id>`.
   Later claims here cite that id.
5. If the project keeps a labbook, `add_labbook_step` with the claim's id
   (berry-labbook-chat.md). `file_claim_in_labbook` files or moves a claim
   already published.

## Documenting a phase

"Document this", "write it up", "the Berry documentation" means claims.
List the phase's findings in order, each with what it rests on and whether
its output is still here (if not: ask for it, or leave it out and say so).
Publish them bottom-up, each citing the earlier ones by their new ids, a
labbook step after each. What they asked to have written down that is not
a finding goes into the labbook's notes, after the claims. Nothing reached
claim level: say so — never prose instead.

## Wrong claims

The researcher's own claim turned out wrong: `review(kind="correction")`
on it, the corrected text in full — never a new copy. A later result that
refutes or extends it under other conditions is a new claim citing it.
