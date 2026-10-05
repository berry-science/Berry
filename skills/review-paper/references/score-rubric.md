# Paper correctness score rubric — v2

*v2 adds the `presentation_weakness` exclusion below. For any review that
contains no `presentation_weakness` finding, v2 and v1 give the identical
score, so scores from earlier runs remain comparable.*

The score is a deterministic function of your findings. Do not adjust it
by feel; apply the rules below and show the arithmetic in
`score_rationale`.

## Computation

1. Start at 100.
2. For every finding with `confidence >= 0.5` whose `error_class` is NOT
   `presentation_weakness`, deduct by severity:
   - `critical`: −40
   - `major`: −25
   - `moderate`: −10
   - `minor`: −3
3. Findings with `confidence < 0.5` are listed but deduct nothing.
4. `presentation_weakness` findings are listed but deduct nothing — at
   any severity and any confidence.
5. Floor the result at 0. The score is an integer.

The score measures **correctness only** — never novelty, significance,
writing quality, or presentation. That is exactly why a weakness deducts
nothing: it is a real observation about the paper, but it is not a claim
that anything in the paper is wrong, and a number that moved for both
would measure neither.

## Severity anchors

- **critical** — invalidates the paper's central claim. The headline
  result is wrong as stated: the main theorem's proof collapses, the
  principal measurement has the wrong sign or magnitude, the core method
  cannot produce the claimed output.
- **major** — a principal result or derivation is wrong, but the central
  claim could survive substantial rework: a sign error propagating
  through a derivation, a wrong statistical test invalidating one of
  several experiments, a key equation inconsistent with the results
  built on it.
- **moderate** — a real, locally-contained error: a wrong constant in a
  non-central equation, a dimensional inconsistency in one expression, a
  number in a table inconsistent with the text, an overclaim in one
  interpretive sentence.
- **minor** — a slip with no effect on any conclusion: a typo in a
  non-load-bearing formula, a rounding inconsistency, a wrongly-typeset
  unit where the accompanying math is right.

On a `presentation_weakness`, severity says how badly the passage
obstructs a reader — `major` for an argument central to the paper that
cannot be followed at all, `minor` for a local muddle — and it still
deducts nothing. Severity there is triage for the authors, not arithmetic.

## Verdict bands (for reference)

The verdict is derived from the score mechanically, never by judgement:
`>= 90` clean, `70–89` minor_issues, `40–69` major_issues,
`< 40` fundamentally_flawed. You output only the number.

## Worked example

Four findings: a major sign error in a central derivation (confidence 0.8,
−25) and a table/text inconsistency (confidence 0.6, −10); a third
suspicion at confidence 0.3 deducts nothing; and a `presentation_weakness`
of severity `major` at confidence 0.9 — an unfollowable argument, but not
an incorrect one — which also deducts nothing.
Score: 100 − 25 − 10 = 65.
