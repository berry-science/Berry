# Worked example: formalize-derivation

A ledger with one **draft** claim, recorded the way the skill describes: a
textbook derivation of the fundamental Gaussian beam (paraxial equation,
1/q, the Gouy prefactor, waist and far-field limits, the near-waist
expansion, a dimension check), its check script, the run's verbatim output
and two exported results.

    claims/
      conventions.json
      2026-10-13-gaussian-beam-paraxial-mode-checks/
        claim.json
        evidence/01-reasoning.md … 07-data.json

`tests/test_formalize_example.py` checks it with `claims.py check` and
re-runs the check script on a copy. Textbook material only.

The output records the helper's hash. After changing the helper, run
`./regenerate.sh` (needs SymPy, mpmath and pint, or uv), review the diff of
`04-output.txt`, and commit the example with the change. The claim stays a
draft: its exports are `format_version 0`.
