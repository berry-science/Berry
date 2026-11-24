# The claim format

## claim.md: what you write

`claims.py new "<title>"` creates `claims/<id>/claim.md` (the id is the date
the finding was made plus a few words) with the header filled as far as it
can. `check` and `seal` compile it into `claim.json` and `evidence/`; never
edit those two by hand — the next compile overwrites them.

```markdown
---
title: Explicit Euler at dt = 0.05 gains 4.0 % energy over 10^4 periods
statement: For the undamped harmonic oscillator (omega = 1), explicit Euler with
 dt = 0.05 increases the total energy by 4.0 % over 10^4 periods; RK4 at the
 same step stays within 1e-9.
type: negative_result
holds_when: Simulation (oscillator.py). omega = 1, x0 = 1, v0 = 0, dt = 0.05,
 10^4 periods; float64.
conventions: units-natural@1
command: python oscillator.py --method euler --method rk4 --dt 0.05
contributors: Claude Code (claude-opus-5-5), NumPy 2.1
anchors: run:euler-dt005
---

Why the statement follows: what was run and compared, and why it is
believed, citing [1], [2] in the order of Cites.

## Evidence
- runs/euler-dt005.log — Run log, verbatim.
- runs/energy.vl.json — Energy over time, Euler vs RK4.
- parameters: runs/params.json — The parameters of the run.
- runs/full-trace.log local-only — Every step's energy.
- claims/2026-11-08-euler-energy-drift/trace-excerpt.txt — The lines used.

## Cites
- uses commit — The code that produced every number here.
- extends 2026-11-02-rk4-energy-conserved — The RK4 baseline compared against.
- uses arxiv:1234.56789 at "Eq. (3)" review sources/arxiv-1234.56789/2026-11-01-eq-3.json — The energy expression.
```

**Header**, between two `---` lines: `key: value`, plain text (no quotes,
not YAML); a long value continues on lines indented by a space. Keys:
`title`, `statement`, `type` (`result`, `method`, `negative_result`,
`calibration`), `holds_when`, `conventions`, `contributors`, `anchors` (these
three comma-separated), `command`, `commit`, and, if the code lives
elsewhere, `repository` (https address) or `repository_path`. `new` writes
`commit` as the HEAD checked out then; without it, HEAD at each compile;
`commit: uncommitted` if the code could not be committed (then put the code
in an evidence item).

**Reasoning**: the text between the header and `## Evidence`; it becomes
`evidence/01-reasoning.md`. `<!-- -->` comments are dropped.

**`## Evidence`**: `- kind: path — caption`, one per line, in reading order.
The path is a file already on disk, from the project root, the repository
root or the claim's folder (in `backticks` if it has spaces; not inside
`evidence/`). `claims.py` copies it under its numbered name and records its
hash. The kind can be left out where the name says it: `.log` `.txt` `.out`
output, `.vl.json` figure, `.tex` derivation, `.csv` `.tsv` data, `.py` and
other code files code. `.json`, `.md`, `.toml`, `.yaml` need it
(`parameters:`, `data:`, `protocol:`, `code:`). A file over 16 000 characters
is an error until marked `local-only` (kept in the ledger, never published),
with an excerpt of the lines the statement uses as its own item.

**`## Cites`**: `- relation target — reason`, one per line, numbered [1],
[2], … in order. The target is an earlier claim's id, `doi:10.…`, `arxiv:…`,
an http(s) URL, `library:<id>` for a Library claim, or `commit` (the commit's
web address, from the header's commit and git's `origin`; `new` adds this
line when there is one). A paper the claim uses adds the passage
`at "Eq. (3)"`, then `review sources/….json` (its source review) or
`standard` (a standard reference value: CODATA, NIST, a textbook constant).

The reason or caption follows ` — `, ` – `, ` -- ` or ` - `. Errors name the
line (`claim.md:14: …`). Once sealed a claim is never compiled again:
`check` fails if `claim.md` changed and warns if a file its evidence was
copied from changed.

## Relations

| `relation` | when this claim … |
|---|---|
| `uses` | takes a number, method, dataset or code from the target |
| `extends` | refines or generalizes the target's finding |
| `replicates` | reproduces the target's finding independently |
| `refutes` | shows the target wrong, or partly wrong |
| `cites` | refers to it for context only |

## Reference: claim.json and the ledger

```
claims/
├── README.md            claims.py index: the list, the graph, conventions, papers checked
├── conventions.json     the project's conventions, versioned (skill conventions)
├── sources/             reviews of passages of papers (skill review-source)
├── audits/              what check-claims found (claims.py audit)
└── <id>/
    ├── claim.md         what you write
    ├── claim.json       compiled from it
    └── evidence/        01-reasoning.md, 02-output.txt, 03-figure.vl.json, …
```

The compiled `claim.json` (Library limits in characters):

| Field | |
|---|---|
| `id`, `status` | the folder name; `draft` or `sealed` |
| `title` | ≤ 300 |
| `statement` | ≤ 2000 |
| `claim_type` | `result`, `method`, `negative_result`, `calibration` |
| `holds_when` | ≤ 2000 |
| `evidence` | ≤ 64 items, `reasoning` first; each `kind`, `file` (`evidence/NN-kind.ext`), optional `format`, `language`, `caption` (≤ 500), `local_only`. Each item ≤ 16 000. |
| `citations` | ≤ 100; exactly one of `local` (ledger id), `claim_id` (Library), `external` (≤ 500); `relation`; `reason` (≤ 500); for a paper `locator` (≤ 200) and `review` or `standard` |
| `conventions` | ≤ 32, `key@version` from `conventions.json` |
| `contributors` | ≤ 16, each ≤ 120; the agent first, with its model id |
| `anchors` | ≤ 64, each ≤ 255: `run:…`, a dataset, `git:<repo>@<hash>` |
| `provenance` | ≤ 8 KB: `repository`, `commit`, `command`, `agent`, `uncommitted`, `repository_path` |
| `compiled_from` | hash of `claim.md`, and each evidence file's source and hash |
| `seal` | set by `seal`: sha256, time, and `checked` — the checker's round it passed in, or `false` if the researcher sealed it with `--without-check` |
| `library` | set when published: `id`, `url`, `visibility`, `published_at` |

The seal covers the core fields, every evidence file, `compiled_from`, the
wording of each named convention version and each cited source review. A
figure is a Vega-Lite spec with its data inline. Files are UTF-8 text.

**A derivation with an executable check** (skill `formalize-derivation`) adds
beside the `derivation` item its check script (`code`, python), the
lockfile `NN-code.py.lock` (`code`, toml), the run's output, and each
exported result as `NN-data.json`. A step that failed as written is kept as
`*.as-written.*`, captioned `As written: …`. Details are in that skill's
`references/formats.md`; `check` runs its coverage check on every claim with
a `derivation` item.

`claims.py new --json` starts the long form instead: `claim.json` and the
evidence files written by hand, in the shape above.
