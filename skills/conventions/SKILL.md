---
name: conventions
description: Keep the project's conventions — units, normalisations, Fourier and sign conventions, what symbols mean — versioned in claims/conventions.json, name them in every claim, and convert a paper's values into them. Use when a ledger starts, when a number depends on a convention, when taking anything from a paper, when the user defines or changes one, and when a factor 2, 2π, √2 or a sign does not fit.
---

# Conventions: what the numbers mean

A number is only checkable against its conventions. A one- and a two-sided
power spectral density differ by 2; a frequency in Hz and one in rad/s by
2π; a `1/e` and a `1/e²` radius by √2. A claim that does not say which it
uses can be right and still be read wrong. So the project keeps its
conventions in one place, every claim names the ones its numbers are
written in, and every paper a claim takes something from is mapped onto
them. All local; publishing a claim sends its conventions with it.

**In a chat window?** Follow [references/chat.md](references/chat.md).

## Where they live

`claims/conventions.json`, committed with the ledger: each convention has a
key, a category and a list of versions. Use `claims.py conv`
(`../claims/scripts/claims.py`), not hand edits:

| Command | |
|---|---|
| `conv list` | the newest version of each |
| `conv add <key> "<statement>" [--category …]` | a new convention, version 1 |
| `conv revise <key> "<statement>" --why "…"` | its next version, with the reason |
| `conv show <key>` | every version, and which claims use each |

Categories: `units`, `fourier`, `normalisation`, `sign`, `notation`,
`definition`, `approximation`, `other`.

## Rules

- **A statement is checkable**: the definition with its normalisation or
  formula and the unit — not *"one-sided PSD"* but *"S_x(f) is one-sided:
  ∫_0^∞ S_x(f) df = ⟨x²⟩, in µm²/Hz"*.
- **Versions only grow.** A change is a new version with its reason; the
  old one stays, because sealed claims were written in it. Never edit a
  version's statement — every sealed claim naming it would fail `check`,
  which is the point.
- **Never guess a convention into the list.** When the ledger starts or the
  first convention-dependent number appears, collect what the project
  already assumes (units in names and comments, `2*np.pi`, FFT
  normalisation, sign of the exponent, the group's papers), add what is
  clear, and ask the researcher about the rest in one message. Only what a
  reader could get wrong by a factor, a sign or a meaning needs one.
- **Every claim names its versions**: `conventions: psd-one-sided@1,
  angular-frequency@2` in `claim.md`. `claims.py check` refuses unknown or
  malformed references and warns on an older version than the newest, or
  on numbers with no conventions named. The seal covers each named
  version's wording.

## A paper's values

Whenever a claim takes a value, equation or method from a paper (skill
`review-source`):

1. Read the paper's conventions for everything the passage depends on —
   from the whole paper, and the work it cites for them.
2. Map each onto the project's: `same`; `transform` with the conversion
   written out (`S_ours(f) = 2 S_paper(f)`, `ω_ours = 2π f_paper`);
   `conflict` when no conversion makes them the same quantity; `unrelated`.
   The mapping goes into the source review's `conventions`.
3. **Convert before using the value**, and show it in the claim's
   reasoning: the paper's number, the conversion, the result. The claim
   names the project's conventions, never the paper's.
4. A `conflict` means the result does not carry over; do not use it
   without a derivation that bridges the two — itself a claim.

A result off from a paper by 2, 2π, √2 or a sign: check conventions first.

## When one changes

`conv revise` with the reason. Sealed claims keep their version (`conv
show` lists which used which); new claims use the new one. A new claim
building on an old one across the change converts the old value in its
reasoning and says so. The labbook's conventions table shows every version
with its reason.
