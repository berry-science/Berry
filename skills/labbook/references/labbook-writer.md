# Write the labbook step for newly sealed claims, in the background

Instructions for a background agent (a subagent) — in Claude Code the
plugin's `berry:labbook-writer`, in Codex or another agent a subagent given
this file. Where nothing can run in the background, the main agent
follows them itself, after answering the user.

You keep the project's labbook, following the `labbook` skill exactly,
while the main agent carries on with the researcher. You cannot see that
conversation.

0. If `labbook/labbook.tex` does not exist, stop and say so: the main
   agent creates the labbook (`labbook.py init`), because only it knows
   the project's title and the researcher's language.
1. Read `labbook/voice.md`. If it is still the template, do not invent a
   voice: write in plain, neutral prose in the language of `labbook.tex`,
   and say in your reply that voice.md needs filling in from the
   conversation.
2. Read `labbook/labbook.tex` in full, so the new step continues the story
   — why it came next — and does not repeat earlier steps.
3. For each claim id you were given: read `claims/<id>/claim.json` and
   its evidence, and the claims and source reviews it cites. Write its
   step as the skill describes: why, what was done, `\claimbox`,
   `\claimfigures`, `\sourcebox` for papers checked, what it means. Never
   copy a claim's text or numbers into the prose beyond what the sentence
   needs; the box shows the claim.
4. Rewrite "where things stand" and update the open points and follow-up
   questions.
5. `labbook.py build` and `labbook.py check`. Fix what fails in your text.
   Every section you add shows its claim with `\claimbox`; write no
   section without one, and nothing about work that has no claim.
6. Do not commit, and do not touch anything outside `labbook/`.

Reply in two or three lines: the sections added, the open points changed,
whether the PDF built — and that `labbook/` is changed and not yet
committed, for the main agent's next commit.
