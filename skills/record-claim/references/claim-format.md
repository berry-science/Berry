# The claim ledger: format

A ledger is a `claims/` folder at the top of the research repository,
committed with it — every file in it, so check that `.gitignore` does not
drop evidence files (`!claims/**` re-includes them). One folder per claim,
named by the claim's id: `YYYY-MM-DD-a-few-words`, where the date is the
day the finding was made (`claims.py new --date`, when it is recorded
later). `claims.py new` makes the folder and picks a free id.

```
claims/
├── README.md                          written by `claims.py index`
├── conventions.json                   the project's conventions, versioned (skill conventions)
├── sources/                           reviews of passages of papers (skill review-source)
├── audits/                            what check-claims found, per claim (claims.py audit)
│   └── arxiv-2502.09437/2026-10-12-eq-12.json
└── 2026-10-10-sta-ramp-removes-com/
    ├── claim.json
    └── evidence/
        ├── 01-reasoning.md
        ├── 02-figure.vl.json
        ├── 03-output.txt
        └── 04-parameters.json
```

## claim.json

```json
{
  "id": "2026-10-10-sta-ramp-removes-com",
  "status": "draft",
  "title": "Simulated STA-type ramp removes the residual CoM oscillation (31.1 → 0.009 µm)",
  "statement": "In the simulated transport, replacing the linear trap ramp by a smooth STA-type ramp (a = b = 0) reduces the residual center-of-mass oscillation at the end of the 30 ms hold from 31.1 µm to 0.009 µm.",
  "claim_type": "result",
  "holds_when": "Simulation (transport_sim). y_coil ramped -5.5063 → -1.5318 A over 200 ms, then a 30 ms hold; noise-free drivers.",
  "evidence": [
    {"kind": "reasoning", "file": "evidence/01-reasoning.md", "format": "markdown"},
    {"kind": "figure", "file": "evidence/02-figure.vl.json", "format": "vega-lite",
     "caption": "CoM position during the hold, linear vs STA ramp."},
    {"kind": "output", "file": "evidence/03-output.txt", "caption": "Run log, verbatim."},
    {"kind": "parameters", "file": "evidence/04-parameters.json", "format": "json"}
  ],
  "citations": [
    {"local": "2026-10-08-linear-ramp-residual", "relation": "extends",
     "reason": "The linear-ramp residual this claim removes."},
    {"external": "https://gitlab.example.org/group/transport_sim/-/commit/9f4be3bce57ca602101efa19c59485dc7c302ca3",
     "relation": "uses", "reason": "The code that produced every number here."},
    {"external": "doi:10.1103/RevModPhys.91.045001", "relation": "uses",
     "locator": "Eq. (34)",
     "review": "sources/doi-10.1103-revmodphys.91.045001/2026-10-09-eq-34.json",
     "reason": "The STA ramp shape."}
  ],
  "conventions": ["angular-frequency@1", "lengths-um@1"],
  "contributors": ["Claude Code (claude-opus-5-5)", "NumPy 2.1"],
  "anchors": ["git:transport_sim@9f4be3bce57ca602101efa19c59485dc7c302ca3", "run:sta-ramp-2026-10-10"],
  "provenance": {
    "repository": "https://gitlab.example.org/group/transport_sim",
    "commit": "9f4be3bce57ca602101efa19c59485dc7c302ca3",
    "command": "pixi run python scripts/current_noise_propagation.py --ramp sta",
    "agent": "Claude Code (claude-opus-5-5)"
  },
  "library": null
}
```

| Field | | |
|---|---|---|
| `id` | set by `new` | Same as the folder name. Never changes. |
| `status` | `draft` or `sealed` | `seal` sets it. A sealed claim is not edited again. |
| `title` | required, ≤ 300 | The finding in one line, not the topic. |
| `statement` | required, ≤ 2000 | What could be false, with the numbers that make it checkable. |
| `claim_type` | recommended | `result`, `method`, `negative_result`, `calibration`. |
| `holds_when` | recommended, ≤ 2000 | Kind of evidence first (simulation, model, measurement), then system, ranges, versions, what was held fixed. |
| `evidence` | required, ≤ 64 | In reading order, `reasoning` first. Each item has `kind`, and `file` (a path inside the claim folder) or inline `content`; optional `format`, `language` (for code), `caption` (≤ 500), `local_only` (kept here, not published). |
| `citations` | recommended, ≤ 100 | What the claim rests on. Each has exactly one target: `local` (another claim in this ledger, by id), `claim_id` (a Berry Science Library claim) or `external` (`doi:10.…`, `arxiv:…`, or an http(s) URL). Plus `relation` and a one-sentence `reason`. For a paper: `locator` (≤ 200, the passage: `"Eq. (12)"`) and `review` (the source review of that passage, a path in `sources/`; its content is covered by the seal) — or `"standard": true` for a standard reference value (CODATA, NIST, a textbook constant), which needs no review; it stays in the ledger and is not published. |
| `conventions` | recommended, ≤ 32 | The conventions its numbers are written in, as `"key@version"` from `conventions.json`. Covered by the seal: the wording of each named version. Published in full with the claim. |
| `contributors` | optional, ≤ 16 | Agents and tools that did the work, the agent first. |
| `anchors` | optional, ≤ 64 | Exact search keys: `run:…`, a dataset name, `git:<repo>@<full-hash>`. |
| `provenance` | optional, ≤ 8 KB | Where it came from: `repository`, full `commit` hash, `command`, `agent`. `"uncommitted": true` if the code could not be committed. `repository_path` if the code is in another local repository than the ledger (used only by `check`). |
| `seal` | set by `seal` | `sha256` over the core fields and every evidence file, and `at`. |
| `library` | set by `published` | `id`, `url`, `visibility`, `published_at` once in the Berry Science Library. Outside the seal. |

## Relations

| `relation` | Use it when this claim … |
|---|---|
| `uses` | takes a number, method, dataset or piece of code from the target |
| `extends` | refines or generalizes the target's finding |
| `replicates` | reproduces the target's finding independently |
| `refutes` | shows the target is wrong, or partly wrong |
| `cites` | refers to it for context only |

## Evidence kinds and file names

| `kind` | File | `format` |
|---|---|---|
| `reasoning` | `NN-reasoning.md` | `markdown` |
| `figure` | `NN-figure.vl.json` | `vega-lite` (data inline), or an image with `asset` when publishing |
| `derivation` | `NN-derivation.tex` | `latex` |
| `code` | `NN-code.py` (any extension) | set `language` |
| `parameters` | `NN-parameters.json` | `json` |
| `output` | `NN-output.txt` | verbatim, as the program printed it |
| `data` | `NN-data.csv` | `csv` |
| `protocol` | `NN-protocol.md` | `markdown` |

`NN` is the item's position, so the folder reads in the same order as the
claim. Files are UTF-8 text.

**A derivation with an executable check** (skill formalize-derivation)
adds to the `derivation` item: the check script (`code`, language
`python`), its lockfile `NN-code.py.lock` (`code`, language `toml`), the
run's output (`output`), and each exported result as `NN-data.json`
(`data`, format `json`). Where the derivation as found had a step that
failed, its `.tex`, script and output are kept beside the corrected ones
as `*.as-written.*`, each with a caption starting `As written:`. That
caption is the marker, because it is published with the item. The
skill's `references/formats.md` has the details; `check` runs its
coverage check on every claim with a `derivation` item.

The Library takes at most 16 000 characters per item. A larger file stays
in the ledger in full with `"local_only": true` on its item, and a shorter
excerpt goes beside it as its own item; publishing leaves local-only items
out. Decide this before sealing: it is part of the claim.
