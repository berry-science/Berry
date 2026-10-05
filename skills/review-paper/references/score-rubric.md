# Paper correctness score rubric — v3

*v3 changes one thing from v2 that moves scores: severity is defined by
what the error costs the paper, not by how large the mistake is. It also
adds `invalid_approximation` and `scope_overreach`, both of which deduct
like any other error class. The arithmetic in §Computation is unchanged,
so a review whose severities v2 and v3 would agree on scores identically.*

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

## Severity is what the error costs, not how big the mistake is

This is the part reviewers get wrong. Severity is **not** a measure of how
large or how obvious the slip is. A one-character typo that propagates
into the paper's headline number is `critical`. A wholly wrong paragraph
in an appendix that nothing depends on is `minor`.

Apply the counterfactual test. **If this were corrected, what else would
change?**

- Nothing else in the paper changes → `minor`.
- One local statement, table entry or equation changes → `moderate`.
- A principal result, figure or derivation changes → `major`.
- The paper's central claim changes → `critical`.

Work it through explicitly for anything you are tempted to call `minor`.
A 16 µs scan range against a 16.6 µs period is a rounding-sized slip, and
if the diffraction phase is what the paper measures, correcting it changes
the paper's central number: that is `major`, not `minor`.

The reverse discipline matters as much. A dimensional error in an
expression that appears once, is never used, and contradicts nothing is
`minor` however offensive it looks.

## Severity anchors

- **critical** — invalidates the paper's central claim. The headline
  result is wrong as stated: the main theorem's proof collapses, the
  principal measurement has the wrong sign or magnitude, the core method
  cannot produce the claimed output, an approximation the central result
  rests on does not hold in the regime used.
- **major** — a principal result or derivation is wrong, but the central
  claim could survive substantial rework: a sign error propagating
  through a derivation, a wrong statistical test invalidating one of
  several experiments, a key equation inconsistent with the results
  built on it, a conclusion drawn well outside the regime that was shown.
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

## Findings are uncapped, and the score is not floored by that

There is no limit on how many findings you report, so there is no limit on
how far the score can fall. Do not manage the number: if fifteen errors
are real, deduct for fifteen and let the score go where the arithmetic
sends it, including to 0. A paper is not entitled to a floor and you must
not soften severities to keep it off one.

The pressure runs the other way too. Because nothing caps the list, a
padded review costs the paper score it should not lose. Every deduction
must trace to a finding that meets the evidentiary bar in the system
prompt.

## Verdict bands (for reference)

The verdict is derived from the score mechanically, never by judgement:
`>= 90` clean, `70–89` minor_issues, `40–69` major_issues,
`< 40` fundamentally_flawed. You output only the number.

## Worked example

Five findings: an `invalid_approximation` the central result rests on
(confidence 0.7, `critical`, −40); a major sign error in a central
derivation (confidence 0.8, −25); a table/text inconsistency (confidence
0.6, `moderate`, −10); a `scope_overreach` where a fitted relation is
extrapolated past its data in one sentence (confidence 0.55, `moderate`,
−10); and a `presentation_weakness` of severity `major` at confidence 0.9
— an unfollowable argument, but not an incorrect one — which deducts
nothing.
Score: 100 − 40 − 25 − 10 − 10 = 15.
