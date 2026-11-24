# Check a paper's passage from a chat window

Use this when you are **not running inside the user's research
repository** — a chat window such as Claude.ai or ChatGPT. There is no
ledger: the review goes straight to the Berry Science Library with the
connector's `review_source` tool, where it is attached to the paper.

## When

Whenever a claim is about to take something from a paper — an equation, a
value, a method — check that passage first. If the researcher is mid-task,
answer their question first and offer the check in one line at the end.

**How much checking** depends on what the claim does with the value:

- a **standard reference value** — CODATA, NIST, a textbook constant: no
  review; cite it with where it is (`locator`);
- **used, but the result does not hinge on it**: a quick check of units,
  conventions and the number as printed, recorded as a short review whose
  `method` says so;
- **what the result depends on**: the full check below.

When unsure, take the deeper check.

## 1. Has someone checked it?

`get_source` with the paper (`arxiv:…`, `doi:…` or a link) and `locator`
for the passage. Read every review of it and its replies. A review is a
lead, not a verdict: check its reasoning. If it found the passage wrong,
start from its proposed fix.

## 2. Get the paper

- If the user attached it (PDF or LaTeX), read it. For a PDF, read the
  equations and tables from the page images, not only from extracted text,
  which garbles mathematics; transcribe an equation into LaTeX yourself and
  say so in `method`.
- If you can open web pages, try the arXiv PDF (`https://arxiv.org/pdf/<id>`).
- Otherwise ask once: *"Can you attach the PDF of <paper>?"* If they
  cannot, the passage stays unchecked: write the review with `read_from:
  "none"` and `verdict: "could_not_check"` only if they want it on record,
  and say in any claim that uses it, in `holds_when`, that the value was
  taken unchecked from the paper.

## 3. Conventions, then the passage

1. Write down every convention the passage depends on (units, 2π, one- or
   two-sided, signs, what each symbol means) from the whole paper — they
   may be defined anywhere.
2. Compare them with the researcher's (`list_my_conventions`; see
   berry-conventions-chat.md): `same`, `transform` with the conversion,
   `conflict`.
3. Check the passage for its use: re-derive it, recompute values with the
   researcher's help if a run is needed (they run the code and paste the
   output), check units and the regime of validity. An apparent error that
   disappears under the paper's own conventions is not an error.

## 4. Record it

First read the summary against the verdict: if the summary finds a
problem the verdict ignores, one of the two is wrong. Show the researcher
the review — passage, verdict, each problem with its fix — and whether
it will be public (recommend public: the next reader of the paper is
who it is for) or private. On their go-ahead, call `review_source` with:

- `source` and `source_version` of the copy you read (a publisher's PDF:
  its DOI; an arXiv copy: its id and version), `locator`, `quote`
  (verbatim), `purpose`;
- `read_from`: `latex`, `pdf`, `html`, `other` or `none`;
- `verdict`: `holds`, `holds_with_correction`, `fails`, `could_not_check`;
- `summary` (problem first), `method`, `conventions` (each with `paper`,
  `where`, `maps_to`, `relation`, `transform`), `items` (one per problem,
  with `proposed_fix` in full);
- `private: true` unless they chose public.

Keep the returned `source_review_id`.

## 5. Build on the corrected version

If the passage is wrong and fixable, publish the corrected version as its
own claim first (berry-publish-claim-chat.md) — citing the paper with
`refutes` and the `locator` — and pass its id as `correction_claim_id`
when writing the review. A claim that needs the passage then cites the
correction claim with `uses`, and the paper with `locator` and
`source_review_id`. Never build on a passage whose verdict is `fails`.
