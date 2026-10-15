# Noticing findings in a chat window

In a chat window — Claude.ai, ChatGPT — there is no hook and nothing runs
in the background: the researcher runs the code elsewhere and pastes the
results back. The habit is the same; only the timing changes.

**After each pasted result, check it against the threshold** — a claim is
a statement that could be false, with the numbers that make it checkable,
from a run in this conversation, under conditions you can name, that the
next step will build on. Negative results and calibrations count. A run
that will be repeated in a minute, a check, a plan do not.

**If it touches a claim already established** — one whose title you
read at the start (berry-recall-chat.md) — compare it with that claim: the
number, the conditions. A result that disagrees with an earlier claim is
said in the answer, with both, whether or not it becomes a claim.

**If it is a claim, answer the researcher's question first, in full.**
Then, as the last line of the same answer, offer to record it — once, in
one sentence, naming the finding:

> *Worth recording: "the STA ramp reduces the residual to 0.009 µm". Shall I
> draft the claim?*

Never open an answer with the offer, never ask twice for the same result,
and never hold back the answer until they reply. If they do not take it up,
carry on; if more findings pile up unrecorded, offer them together at a
natural pause: *"Three results from today are not recorded yet: …"*.

**Before the next step builds on an unrecorded result**, say so in one
sentence — that is the one time it is worth raising mid-task.

## Documenting a phase

When the researcher asks to document, write up or record a phase, a day's
work or "the Berry documentation", the job is the claims. The labbook
follows from them; it never replaces them.

1. **List the findings.** Go back through the phase and list each result
   that meets the threshold above, one line each, in the order it was
   made. Negative results and calibrations count.
2. **For each, what it rests on**: which of the others it uses — a value,
   a setting, a calibration, a conclusion — which earlier claims
   (berry-recall-chat.md), which papers. In a phase that built step by
   step, most findings use an earlier one. One that uses nothing gets a
   sentence saying why.
3. **For each, its evidence**: the output, verbatim, still in this
   conversation, and the code that produced it. If the output is gone —
   only a summary, a number mentioned in passing — ask the researcher to
   paste it or rerun. Otherwise that finding is not recorded; say so.
   Never rebuild evidence from a summary.
4. **Show the list** — finding, rests on, evidence there or missing — and
   ask which to record.
5. **Draft them, then confirm once**: every chosen finding drafted and
   checked, shown in one message, with one go-ahead for the whole list
   (berry-publish-claim-chat.md, "Several claims at once"). Then publish
   them from the bottom up — first the ones that rest on nothing in the
   list, each later one citing the earlier ones by the Library id they
   were just given.
6. **The labbook**: one step per claim, as each is published.
7. **Anything else they asked to have written down** that is not a
   finding — context, decisions, remarks — goes into the labbook's notes,
   at the end, after the claims (berry-labbook-chat.md). Say that these
   are notes, not claims.

If nothing in the phase reaches claim level, say so. Never write prose in
its place.

Drafting and publishing then follow the publish-claim chat procedure
(berry-publish-claim-chat.md): the evidence from what was pasted, the code
as it ran, shown to the researcher before anything is published.
