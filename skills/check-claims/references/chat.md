# Check claims from a chat window

For Claude.ai, ChatGPT and similar, where the claims are in the
[Berry Science Library](https://berry.science/library) and you read them
with the Berry Science connector. Checking writes nothing.

## When

Trust published claims by default: each was checked before it was
published (berry-claims-chat.md) and cannot change. Check one only for a
reason — the researcher asks; `get_claim` shows something new (a review,
a correction, `source_problems` on a paper it cites); it is someone else's
and a new claim is about to rest on it; a result here contradicts it. Then
check that claim and only the part of its chain the reason points to. For
a full audit, say how many claims it covers first.

## How

`get_claim` reads a claim with its evidence, citations and reviews; follow
each cited `claim_id` down for the chain, bottom first. `list_my_claims`,
`search`, `find_literal` find the rest. Read every evidence item, then for
each claim on its own:

- Is each number in the statement in the evidence, with the rounding right?
- Does the statement follow, with nothing stronger than what was run?
- Is `holds_when` no broader than what was run?
- Is everything it uses cited, and does each cited claim say what this one
  takes from it? A paper's passage: `get_source` — checked, and with what
  verdict?
- Uncommitted code: does it compute what the statement reports, and did it
  run unchanged? Numbers consistent with the stated `conventions` (a factor
  2, 2π or a sign is a finding)?

Not whether it is interesting, novel or well written. Then the chain: a
weak claim weakens everything that `uses` it — say which.

## Report and answer

Per claim with findings: id and title; each finding **quoting** the exact
text it is about, why it is wrong, and `minor`, `moderate` or `major`. Then
the claims with no findings — a good result; a false alarm costs as much
as a miss.

Nothing in the Library is edited. An error in the researcher's own claim
is answered with `review(kind="correction")`, the fix in full; in someone
else's, with `review(kind="review_report")`, one item per issue, posted
under the researcher's name only on their go-ahead.
