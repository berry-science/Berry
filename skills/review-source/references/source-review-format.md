# A source review: format

One file per review, in the ledger, under the paper it reviews:

```
claims/
└── sources/
    └── arxiv-2502.09437/                 the paper's key, as a folder name
        ├── 2026-10-12-eq-12.json         one passage, for one use
        └── 2026-10-14-table-ii.json
```

`claims.py source new <paper> --locator "…"` creates the file with every
field present and empty, and prints its path. The paper may be given as
`arxiv:2502.09437v2`, `doi:10.…`, or an arxiv.org / doi.org link: the
review is filed under the paper's **key** — arXiv without the version,
DOI in lower case — and the version goes into `source_version`. This is the
same key berry.science files reviews under, so a review published from
here lands beside everyone else's reviews of the same paper.

## The file

```json
{
  "source": "arxiv:2502.09437",
  "source_version": "v2",
  "locator": "Eq. (12)",
  "quote": "\\omega_\\perp = \\sqrt{k_\\perp / m}",
  "purpose": "The radial trap frequency the transport simulation takes as input.",
  "read_from": "latex",
  "verdict": "holds_with_correction",
  "summary": "Eq. (12) gives the trap frequency in Hz (f), not ω: the 2π of Eq. (9) is dropped. With it, the quoted 1.5 kHz is ω/2π = 1.5 kHz, i.e. ω = 9.42 kHz.",
  "method": "Re-derived (12) from (9)–(11); recomputed with the parameters of Table I (code in the correction claim).",
  "conventions": [
    {"paper": "Frequencies are in Hz throughout (f = ω/2π).",
     "where": "Sec. 2, below Eq. (3)",
     "maps_to": "angular-frequency@1", "relation": "transform",
     "transform": "ω_ours = 2π f_paper"}
  ],
  "items": [
    {"quote": "\\omega_\\perp = \\sqrt{k_\\perp / m}",
     "body": "Units: with k in N/m and m in kg the right side is in rad/s, but the text quotes the result in Hz; Eq. (9) defines ω = 2πf.",
     "severity": "major",
     "error_classes": ["unit_dimension"],
     "proposed_fix": "\\omega_\\perp = 2\\pi f_\\perp,\\quad f_\\perp = \\frac{1}{2\\pi}\\sqrt{k_\\perp/m}",
     "proposed_fix_format": "latex"}
  ],
  "correction": {"local": "2026-10-12-corrected-trap-frequency"},
  "reviewer": {"agent": "Claude Code (claude-opus-5-5)", "human": "G. Müller"},
  "date": "2026-10-12",
  "library": null
}
```

| Field | | |
|---|---|---|
| `source` | required | The paper's key. Set by `source new`; `check` refuses another spelling. |
| `source_version` | recommended | What was read: `v2`, a journal volume, a date. |
| `locator` | recommended, ≤ 200 | The passage. Empty only for a review of the whole paper. |
| `quote` | recommended, ≤ 2000 | The passage verbatim: LaTeX from the source, or transcribed from the PDF (say so in `method`). |
| `purpose` | recommended, ≤ 1000 | What the passage is used for. A passage can be right for one use and wrong for another. |
| `read_from` | required | `latex`, `pdf`, `html`, `other`, or `none` when the paper could not be obtained. |
| `verdict` | required | `holds`, `holds_with_correction`, `fails`, `could_not_check`. With `read_from: "none"`, only `could_not_check`. |
| `summary` | required, ≤ 4000 | What was found, the problem first. |
| `method` | recommended, ≤ 500 | How it was checked: re-derived, recomputed, units. |
| `conventions` | recommended, ≤ 32 | The paper's conventions the passage depends on: `paper` (in its terms), `where`, `maps_to` (the project's, as `key@version`), `relation` (`same`, `transform`, `conflict`, `unrelated`), `transform` (required for `transform`). |
| `items` | one per problem, ≤ 64 | `quote`, `body` (what is wrong and how you know), `severity` (`minor`, `moderate`, `major`, `critical`), `error_classes` (from review-paper), `proposed_fix` (in full), `proposed_fix_format`. |
| `correction` | for a corrected passage | `{"local": "<claim id>"}`: the claim carrying the corrected version. |
| `reviewer` | | `agent` (with the exact model id), `human` (who also checked it, if anyone). |
| `date` | | When the review was done. |
| `library` | set by `source published` | The Library id and the paper's page. Outside the seal of citing claims. |

## Citing it from a claim

A citation of the paper names the passage and the review:

```json
{"external": "arxiv:2502.09437v2", "relation": "uses", "locator": "Eq. (12)",
 "review": "sources/arxiv-2502.09437/2026-10-12-eq-12.json", "reason": "…"}
```

`claims.py check` then:

- refuses a review of another paper, and a claim that `uses`, `extends` or
  `replicates` a passage whose review `fails`;
- warns when the verdict is `holds_with_correction` and the claim does not
  also cite the correction claim, and when it is `could_not_check`;
- warns on any claim that `uses` a `doi:` or `arxiv:` work without a
  `locator` or without a review.

The citing claim's seal covers the review's content (not its `library`
field): changing the review afterward fails `check`.
