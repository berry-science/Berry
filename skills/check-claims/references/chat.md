# Check claims from a chat window

Use this when you are **not running inside the user's research
repository** — a chat window such as Claude.ai or ChatGPT — and the claims
are in the [Berry Science Library](https://berry.science/library) rather
than in a local ledger. You read them with the Berry Science connector's
read tools; checking needs no permission to write.

## When to check — and when not

**Trust published claims by default.** A claim is checked once, before it
is published (berry-publish-claim-chat.md), and cannot change afterward.
Re-reading it every time a new claim builds on it costs the researcher's
time and finds nothing new.

So check a claim already in the Library **only when there is a reason**:

- the researcher asks you to;
- `get_claim` shows something that was not there when it was published:
  a review (`review_count`, `candidate_issues`), a correction by its
  author, a cited paper with a passage found wrong (`source_problems`);
- the claim is someone else's, and a new claim is about to rest on it;
- a result in this conversation contradicts it.

Then check that claim — and only the part of the chain the reason points
to, not everything below it. Never walk all of the researcher's claims, or
a whole chain, on your own initiative. When the researcher asks for a full
audit, say how many claims it covers before you start.

## Find the claims

- One claim: `get_claim` with its id. It returns the statement, evidence,
  citations, and any reviews.
- What it rests on: for each citation with a `claim_id`, `get_claim` on
  that id, and so on down. That is the chain to check, bottom first.
- The user's claims: `list_my_claims`; by subject: `search`.

## Each claim on its own

Read the whole claim — every evidence item — and answer, for this claim
alone:

1. **Is each number in the statement in the evidence?** In the output, the
   data, a figure's inline data. A number only in the reasoning is not
   evidenced. Rounding must be right.
2. **Does the statement follow** from the reasoning and the material
   together? Look for a step that does not follow, a comparison against
   something not shown, a conclusion stronger than the evidence.
3. **Does `holds_when` match** what was run: system, ranges, versions?
4. **Is every step cited?** A value, method or result it uses must be in
   its citations. Name what is missing. Look for it: a value in the
   reasoning that is in neither its evidence nor a cited claim; a claim
   that cites no earlier claim while the researcher's earlier claims on
   the same subject exist (`search` for them).
5. **Do the citations say what they are used for?** Open a cited claim and
   check it states what this one takes from it.
6. **The code.** If `provenance` says `uncommitted`, the code in the
   evidence is all there is: does it actually compute what the statement
   reports, with the stated parameters? Is `ran_unchanged` true? A
   `git-blob:` anchor can be matched to a commit later; say whether it is
   there.
7. **Conventions.** Are the numbers consistent with the `conventions` the
   claim states? A factor 2, 2π or a sign that only works under another
   convention is a finding.
8. **The papers it uses.** For each cited paper, `get_claim` reports
   `source_reviews` and `source_problems`; if either is non-zero, read them
   with `get_source`. Was the passage this claim uses (`locator`) checked,
   and with what verdict? Does the claim build on a passage someone found
   wrong?

Do not judge whether the finding is interesting, novel or well written.

## The chain

Does the top result still hold given what you found below it? A weak claim
at the bottom weakens everything that `uses` it — say which.

## Reporting

Per claim with findings: the id and title; each finding, **quoting** the
exact text from the claim or the evidence item it is about, why it is wrong,
and how much it matters — `minor`, `moderate` or `major`; and for a gap,
what would close it. Then list the claims with no findings. No findings is
a good result; a false alarm costs as much as a miss.

A claim in the Library cannot be edited. A fix is a new claim that cites
the old one with `refutes` or `extends`, published with the user's
go-ahead (publish-claim, chat mode).
