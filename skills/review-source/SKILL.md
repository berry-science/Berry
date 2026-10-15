---
name: review-source
description: Check the passage of a paper a claim takes something from — an equation, a value, a method — against the paper's conventions and the project's, record it as a source review, and build on a corrected version if it is wrong. Use before a claim uses something from a paper, when the user asks to check part of a paper, and when a paper's value does not fit the project's results.
---

# Review the passage of a paper a claim rests on

A claim that `uses` a paper rests on one passage of it: Eq. (12), the value
in Table II, the step from (4) to (5). If that passage is wrong, or written
in other conventions than the project's, everything built on it is wrong
with it. This skill checks **that passage**, for **that use**, and records
the check as a **source review**: attached to the paper, permanent, and —
once published — shown to everyone who reads or cites the same paper on
berry.science.

**How much checking a value needs** depends on what the claim does with
it:

| The value is | Check | Recorded as |
|---|---|---|
| A **standard reference value** — CODATA, NIST, a textbook constant | none | the citation, with `"standard": true` and where it is (`"locator": "CODATA 2018"`) |
| **Used, but the result does not hinge on it** — a parameter, an order of magnitude | a quick check: the units, the conventions, the number as printed | a short source review: `method` says it was a quick check |
| **What the result depends on** — the equation it builds on, the value it is compared with | everything below | a full source review |

When unsure, take the deeper check.

This is not `review-paper`. That skill referees a whole paper and scores
it. This one checks what a claim takes, as deeply as the claim needs, and
nothing else. Reuse its standard: the error classes and the evidentiary bar
in `../review-paper/SKILL.md` apply to every finding here.

**In a chat window?** Follow [references/chat.md](references/chat.md).

The file format is in
[references/source-review-format.md](references/source-review-format.md).
The commands are the ledger's own (`claims.py source …`, in
`../record-claim/scripts/`).

## Can run in the background

A source review takes a while and the researcher need not wait for it.
Start it as a background agent with
[references/source-reviewer.md](references/source-reviewer.md) as its
instructions (in Claude Code: `berry:source-reviewer`), with the paper,
the passage, what it is used for and the project's conventions, and carry
on. The claim that uses the passage is drafted meanwhile; it is sealed
only after the verdict is in.

What follows is the full check; a quick check does steps 1, 2 and 3 and
records the review (step 5) without re-deriving.

## 1. Has someone checked it already?

If the Berry Science connector is available, `get_source` with the paper
(and `locator` for the passage). Read every review of that passage and its
replies. A review is a candidate, not a verdict you can adopt unread: check
its reasoning against the paper. If it holds, your review can be short and
say so — and reply to it (`parent_id`) rather than repeat it. If it found
the passage wrong, start from its proposed fix.

Also `claims.py source list <paper>` for reviews already in this ledger.

## 2. Get the paper

In this order, and stop at the first that works:

1. **LaTeX source** — best: every finding quotes the source. For arXiv,
   download `https://arxiv.org/e-print/<id>` (add the version, `…v2`, when
   the claim uses a specific one) into a fresh empty directory outside the
   ledger, e.g. `.berry/papers/<paper>/`, and unpack it (a gzipped tarball,
   sometimes a single gzipped `.tex`).
2. **The PDF** — `https://arxiv.org/pdf/<id>`, or the publisher's PDF if it
   is open. Extract the text (`pdftotext -layout`, or a PDF reading tool),
   and **look at the page images** for every equation and table you check:
   extracted text garbles mathematics, sub- and superscripts, and table
   columns. Quote the passage as printed; transcribe an equation into LaTeX
   yourself and say in `method` that it was transcribed from the PDF.
3. **Ask the researcher.** If neither can be downloaded — a paywall, no
   network, a DOI that resolves to a landing page — ask once (in the
   setup message, if this is the project's first claim), in one
   sentence: *"I cannot get <paper>; can you put the PDF or source in the
   project (e.g. `.berry/papers/`)?"* Carry on with other work meanwhile.
4. **If they cannot**, record the review anyway with `read_from: "none"`
   and `verdict: "could_not_check"`: the claim then says, through its
   citation, that the passage it uses was not checked. `claims.py check`
   warns on every claim that uses it, until someone checks it.

Never commit downloaded papers to the repository unless the researcher
says so: add `.berry/` to `.gitignore` (ask first; it is their file).

## 3. Read the conventions the passage depends on

Before judging the passage, write down every convention it depends on —
symbols, units, factors of 2 and 2π, one- vs two-sided spectra, signs,
normalizations, which quantity a name means — **from the whole paper**:
a convention may be declared anywhere, even after the passage, or in the
work it cites (the full list of what to look for is in `review-paper`,
Step 1).

Then compare each with the project's conventions (`claims.py conv list`,
skill `conventions`) and record the mapping: `same`, `transform` (with the
conversion, e.g. `S_ours(f) = 2 S_paper(f)`), `conflict`, or `unrelated`.
A value taken from the paper is only usable after its transform — that is
part of the result of this review, and the claim that uses the value cites
it.

## 4. Check the passage, for its use

- **Re-derive** an equation from the paper's earlier steps; **recompute** a
  value from its inputs (with code, and keep the code as the review's
  `method` or the correction claim's evidence); **check units** and
  limiting cases; check the passage's **regime of validity** against the
  regime the claim uses it in.
- Check what the claim needs, as deeply as it needs it. A value used as an
  order of magnitude needs less than one the claim's result depends on to
  three digits.
- Hold findings to the evidentiary bar of `review-paper`: an apparent error
  that disappears under the paper's own conventions is not an error. False
  alarms cost as much as misses.

## 5. Record it

```bash
claims.py source new <paper> --locator "Eq. (12)"     # prints sources/<paper>/<file>.json
```

Fill in the file (format reference): the passage verbatim in `quote`, what
it is used for in `purpose`, what you read in `read_from`, the conventions
and their mapping, one item per problem with the corrected version in full
in `proposed_fix`, a `summary` that states the problem first, `method`, and
`reviewer` (yourself with your exact model id; the researcher as `human` if
they checked it too). Then `claims.py check sources/<paper>/<file>.json`.

**The verdict:**

| Verdict | When | Then |
|---|---|---|
| `holds` | Checked, and right for this use | The claim cites the paper with `locator` and `review` |
| `holds_with_correction` | Wrong as printed, and you can fix it | Record the corrected version as its own claim (below); build on that |
| `fails` | Wrong, and not fixable here | Nothing may `use` it; `check` refuses a claim that does |
| `could_not_check` | Not obtainable, or the check could not be done | The claim may use it, and says so in `holds_when` |

## 6. A wrong passage: correct it, and build on the correction

1. Record the corrected passage as a claim (skill `record-claim`): the
   corrected equation or value as the statement, the derivation or the
   recomputation as evidence, citing the paper with relation `refutes` and
   the `locator`. Seal it once the researcher agrees.
2. Name it in the review: `"correction": {"local": "<claim id>"}`.
3. The claim that needed the passage then cites **both**: the correction
   claim with `uses`, and the paper with `cites` or `uses` plus `locator`
   and `review`. `check` warns if the correction is not cited.

## 7. Cite it from the claim

```json
{"external": "arxiv:2502.09437v2", "relation": "uses", "locator": "Eq. (12)",
 "review": "sources/arxiv-2502.09437/2026-10-12-eq-12.json",
 "reason": "The trap frequency, after the 2π correction of claim [2]."}
```

The review is covered by the citing claim's seal: changing it afterward
fails `check`. Publishing it later does not.

## 8. Share it (optional)

Everything above works without berry.science: the review lives in the
ledger, `check` enforces it, the labbook shows it. Sharing needs the
Berry Science MCP connection and the researcher's go-ahead.

A source review is most useful published: it then appears on the paper's
page on berry.science and in every `get_claim` of a claim citing the
paper. Publishing follows `publish-claim`: `claims.py order <claim>` lists
source reviews (as `sources/…` paths) before the claims that cite them,
and the correction claim before its review. For a review:
`claims.py source payload <path>` → `review_source` →
`claims.py source published <path> <id>`.

Ask the researcher where it goes. Recommend **public**: a review of a
published paper reveals little, and the next person using the paper is
who it is for. Private is the default when they do not say.

## Rules

- **One passage per review**, for one use. Another equation of the same
  paper is another review; another use of the same equation may be too.
- **Quote, do not paraphrase.** The passage verbatim, and each problem
  quoted where it is.
- **A review once cited by a sealed claim is not edited.** A new insight is
  a new review; on berry.science, a reply to the old one.
- **Someone else's review is a lead, not evidence.** Check it before
  relying on it.
