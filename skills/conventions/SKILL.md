---
name: conventions
description: Keep the project's conventions — units, normalizations, Fourier and sign conventions, what symbols mean — versioned in claims/conventions.json, name them in every claim, and map each paper's onto them. Use when starting a ledger, when a number depends on a convention, when taking anything from a paper, when the user defines or changes one, and when a factor 2, 2π or a sign does not fit.
---

# Conventions: what the numbers mean

A number is only checkable against its conventions. A one-sided and a
two-sided power spectral density differ by a factor 2; a frequency in Hz
and one in rad/s by 2π; a `1/e` radius and a `1/e²` radius by √2. A claim
that does not say which it uses can be right and still be read wrong — by
a colleague, by the next claim, by someone who takes the value into a
paper with the other convention.

So the project keeps its conventions in one place, every claim names the
ones its numbers are written in, and every paper a claim takes something
from is compared against them.

Local and offline: the conventions live in the ledger, and nothing here
needs berry.science. Publishing a claim later sends its conventions with
it.

**In a chat window?** Follow [references/chat.md](references/chat.md): the
conventions then live with the claims in the Berry Science Library.

## Where they live

`claims/conventions.json`, committed with the ledger. Each convention has a
**key** and a list of **versions**:

```json
{"conventions": [
  {"key": "psd-one-sided", "category": "normalisation", "versions": [
    {"version": 1, "statement": "S_x(f) is one-sided: ∫_0^∞ S_x(f) df = ⟨x²⟩, in µm²/Hz.",
     "since": "2026-10-08"}
  ]},
  {"key": "angular-frequency", "category": "units", "versions": [
    {"version": 1, "statement": "Trap frequencies are angular, ω in rad/s; f = ω/2π only where named f.",
     "since": "2026-10-08"},
    {"version": 2, "statement": "Trap frequencies are given as f in Hz; ω = 2πf where named ω.",
     "since": "2026-10-11", "why": "The lab's drivers and the group's papers use f."}
  ]}
]}
```

Written with the ledger's script (`../record-claim/scripts/claims.py`):

| Command | |
|---|---|
| `conv list` | The newest version of each |
| `conv add <key> "<statement>" [--category …]` | A new convention, as version 1 |
| `conv revise <key> "<statement>" --why "…"` | A changed convention: its next version |
| `conv show <key>` | Every version, and which claims use each |

**A statement is checkable**: the definition, with the normalization or
the formula, and the unit — not *"one-sided PSD"* but *"∫_0^∞ S df = ⟨x²⟩,
in µm²/Hz"*. Categories: `units`, `fourier`, `normalisation`, `sign`,
`notation`, `definition`, `approximation`, `other`.

**Versions only grow.** A changed convention is a new version with the
reason; the old one stays, because sealed claims were written in it. Never
edit a version's statement: every sealed claim that names it fails `check`
afterward, which is the point.

## Setting them up

When a ledger starts, or the first claim with a convention-dependent number
is drafted:

1. Collect what the project already assumes: from the code (units in
   variable names and comments, `2*np.pi`, FFT normalization, sign of the
   exponent), from the researcher's messages, from the group's papers.
2. Propose the list in a few lines — the statement of each — in the
   first claim's setup message (skill `record-claim`), and add what they
   confirm with `conv add`. Ask there about the ones you could not
   determine; do not guess a convention into the list.
3. Add more as they come up. Not every symbol needs one: only what a
   reader could get wrong by a factor, a sign, or a meaning.

## In every claim

`claim.json` names the versions its statement and evidence are written in:

```json
"conventions": ["psd-one-sided@1", "angular-frequency@2"]
```

`claims.py check`:

- refuses a reference that is not `key@version` or not in
  `conventions.json`, and a key named twice;
- warns when a draft uses an older version than the project's newest;
- warns, once the project has conventions, when a statement has numbers
  but names none.

The seal covers the wording of each version a claim names. Publishing
sends them with the claim, in full, so the Library copy says what its
numbers mean.

## Against a paper

Whenever a claim takes a value, an equation or a method from a paper
(skill `review-source`):

1. Read the paper's conventions for everything the passage depends on —
   from the whole paper, and from the work it cites for them.
2. Map each onto the project's: `same`; `transform`, with the conversion
   written out (`S_ours(f) = 2 S_paper(f)`, `ω_ours = 2π f_paper`);
   `conflict` when no conversion makes them the same quantity; `unrelated`.
   This mapping goes into the source review's `conventions`.
3. **Apply the transform before using the value**, and show it in the
   claim's reasoning: the paper's number, the conversion, the result. The
   claim names the project's conventions, never the paper's.
4. A `conflict` means the paper's result does not carry over as it is:
   say so in the review and do not use it without a derivation that
   bridges the two — itself a claim.

When a run's result disagrees with a paper by a factor 2, 2π, √2 or a sign,
check the conventions before anything else.

## When a convention changes

1. `conv revise <key> "…" --why "…"` — the reason in a sentence.
2. Sealed claims keep their version; nothing about them changes. `conv show
   <key>` lists which claims were written in which.
3. New claims use the new version. If a new claim builds on an old one
   across the change, its reasoning converts the old claim's value — and
   says so.
4. In the labbook, the conventions table shows every version with its
   reason, so a reader sees when and why it changed.
