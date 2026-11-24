---
name: review-source
description: Check the passage of a paper a claim takes something from — an equation, a value, a method — against the paper's conventions and the project's, and record it as a source review in claims/sources/. Use before a claim uses something from a paper, when the user asks to check part of a paper, and when a paper's value does not fit the project's results.
---

# Review the passage of a paper a claim rests on

A claim that `uses` a paper rests on one passage of it — Eq. (12), a value
in Table II, the step from (4) to (5). If that passage is wrong, or in other
conventions than the project's, everything built on it is wrong too. This
skill checks **that passage, for that use**, and records a **source
review**: a file in `claims/sources/`, attached to the paper, and once
published shown to everyone who reads or cites the paper on berry.science.

Not `review-paper` (a whole-paper referee), but its error classes, its
conventions list (Step 1) and its evidentiary bar (`../review-paper/SKILL.md`)
apply to every finding: an apparent error that disappears under the paper's
own conventions is not an error.

**In a chat window?** Follow [references/chat.md](references/chat.md).
Format and what `check` enforces:
[references/source-review-format.md](references/source-review-format.md).
Commands: `claims.py source …`, `conv list`, `check`
(`../claims/scripts/claims.py`).

**How deep** depends on what the claim does with the value: a standard
reference value (CODATA, NIST, a textbook constant) needs no review — cite
it with `standard` and where it is; a value the result does not hinge on
gets a quick check (units, conventions, the number as printed; `method`
says so); what the result depends on gets the full check. When unsure, go
deeper.

**In the background**: start `berry:source-reviewer` (elsewhere a subagent
given [references/source-reviewer.md](references/source-reviewer.md)) with
the paper, passage, use and conventions, and carry on. The claim can be
written meanwhile; it is not sealed before the verdict.

## The check

1. **Already checked?** `claims.py source list <paper>`, and `get_source`
   (with `locator`) when the Berry Science MCP server is connected. Another
   review is a lead, not evidence: check its reasoning; if it holds, yours
   can be short; if it found the passage wrong, start from its fix.
2. **Get the paper**, best first: the LaTeX source (arXiv
   `https://arxiv.org/e-print/<id>[vN]`); else the PDF — and read every
   equation and table you check from the **page images**, since extracted
   text garbles mathematics (say in `method` that you transcribed it); else
   ask the researcher once, in one sentence, to put it in `.berry/papers/`,
   and carry on with other work; if they cannot, record `read_from: "none"`,
   `verdict: "could_not_check"`.
3. **Conventions first**, from the whole paper (they may be declared after
   the passage, or in work it cites), mapped onto `claims.py conv list`:
   `same`, `transform` with the conversion, `conflict`, `unrelated` (skill
   `conventions`). A value is usable only after its transform.
4. **Check the passage for its use**: re-derive it from the paper's earlier
   steps, recompute values with code, check units, limiting cases and the
   regime of validity against the regime the claim uses it in.
5. **Record it**: `claims.py source new <paper> --locator "Eq. (12)"`, fill
   it in, `claims.py check sources/<paper>/<file>.json` until clean.

| Verdict | When | Then |
|---|---|---|
| `holds` | right for this use | the claim cites the paper with `locator` and `review` |
| `holds_with_correction` | wrong as printed, fixable | the fix becomes its own claim; build on that |
| `fails` | wrong, not fixable here | nothing may `use` it; `check` refuses a claim that does |
| `could_not_check` | not obtainable, or not checkable | the claim may use it, and says so in `holds_when` |

**A wrong but fixable passage**: write the corrected equation or value as a
claim (skill `claims`) with the derivation or recomputation as evidence,
citing the paper with `refutes` and the `locator`; name it in the review
(`"correction": {"local": "<id>"}`). The claim that needed the passage
cites both: the correction with `uses`, and the paper with `locator` and
`review`.

## Hard rules

- **Name the copy you actually read, with its version**: the journal's DOI
  for a publisher's PDF, `arxiv:<id>v<n>` for an arXiv copy. They can differ
  in the very passage you check.
- **Papers go in `.berry/papers/`, never committed**: `.berry/` belongs in
  `.gitignore` (ask first; it is the researcher's file).
- **The researcher's email** goes to a lookup service (Unpaywall, say) only
  after asking them once; keep the answer in `.berry/email` (the address,
  or `no`) and never send it without that answer.
- **Read the summary against the verdict** before `check`: a summary that
  finds a problem the verdict ignores means one of them is wrong.
- **A claim may only `use` a passage that a review covers** — the review
  cited with the passage's `locator`.
- One passage per review, for one use, quoted verbatim. A review cited by a
  sealed claim is never edited: a new insight is a new review.

## Publishing

Nothing here needs berry.science. When a claim is published, `claims.py
publish` first publishes the source reviews it cites (and a correction
claim before its review) over HTTP, read back and verified, to the same
place as the claim — private by default. A review no claim cites (a
`fails`, say) is shared by hand if the researcher wants it: `claims.py
source payload <path>` (`--public` if they choose — a review of a published
paper reveals little, and the next reader of the paper is who it helps) →
the MCP `review_source` → `claims.py source published <path> <id>`.
