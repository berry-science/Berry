# Check a paper's passage from a chat window

For Claude.ai, ChatGPT and other chats outside the research repository.
There is no ledger: the review goes straight to the Berry Science Library
with the connector's `review_source`, attached to the paper.

Before a claim takes something from a paper — an equation, a value, a
method — check that passage. If the researcher is mid-task, answer first
and offer the check in one line. **How deep**: a standard reference value
(CODATA, NIST, a textbook constant) needs no review, only its `locator`; a
value the result does not hinge on gets a quick check of units, conventions
and the number as printed (`method` says so); what the result depends on
gets the full check. When unsure, go deeper.

1. **Already checked?** `get_source` with the paper (`arxiv:…`, `doi:…` or
   a link) and the `locator`. Every review there is a lead, not a verdict:
   check its reasoning; if it found the passage wrong, start from its fix.
2. **The paper**: read it if attached; for a PDF, read equations and tables
   from the page images (extracted text garbles mathematics) and say in
   `method` that you transcribed them. If you can open web pages, try
   `https://arxiv.org/pdf/<id>`. Otherwise ask once for the PDF. If they
   cannot, record a review with `read_from: "none"` and `could_not_check`,
   and a claim using the passage says in `holds_when` that it is unchecked.
3. **Conventions first**, from the whole paper, compared with
   `list_my_conventions` (berry-conventions-chat.md): `same`, `transform`
   with the conversion, `conflict`.
4. **Check the passage for its use**: re-derive, recompute (the researcher
   runs code if needed and pastes the output), units, regime of validity.
   An apparent error that disappears under the paper's own conventions is
   not an error.
5. **Record it.** Read the summary against the verdict first. Show the
   researcher the passage, verdict and each problem with its fix, and ask
   public or private (public helps the next reader of the paper; private if
   they do not say). Then `review_source` with: `source` and
   `source_version` of the copy you read (publisher's PDF: its DOI; arXiv:
   id and version), `locator`, `quote` (verbatim), `purpose`, `read_from`,
   `verdict` (`holds`, `holds_with_correction`, `fails`,
   `could_not_check`), `summary` (problem first), `method`, `conventions`,
   `items` (one per problem, `proposed_fix` in full), `private`. Keep the
   returned `source_review_id`.

**A wrong but fixable passage**: publish the corrected version as its own
claim first (berry-claims-chat.md), citing the paper with `refutes` and the
`locator`, and pass its id as `correction_claim_id`. A claim needing the
passage then cites the correction with `uses` and the paper with `locator`
and `source_review_id`. A claim may only use a passage a review covers;
never one whose verdict is `fails`.
