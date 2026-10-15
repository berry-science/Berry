# Numeric, exact-point and limit checks

## Random points

Every `step` is evaluated at random points of the declared domain, chosen
from the run's seed (`begin(seed=…)`, printed in the header):

- `positive` / `nonnegative`: rationals in [0.35, 2.4]; `negative` the
  same, negated; `integer`: 1 to 5;
- `real`: the same magnitudes with either sign;
- no assumptions (complex): one point on the negative real axis, where
  principal branches cut, then points with random signs and imaginary
  parts.

Values are substituted exactly and evaluated with SymPy's arbitrary
precision (`begin(dps=30)`, `points=5`). A difference larger than
10^−(dps−10) relative to the size of the two sides is re-evaluated at twice
the precision before it counts: a disagreement that survives is a `FAIL`,
with the point and the value printed. Points where either side is not
finite are skipped and replaced.

Agreement at every point is `numeric-consistent`, **never proved**. For a
rational function, agreement at random points is close to proof
(Schwartz–Zippel); for transcendental expressions it is not, which is why
the verdict does not distinguish them.

## Exact points

For an algebraic expression (no exp, log, trig; no π), the difference at
each rational point is an algebraic number, and its minimal polynomial
decides exactly whether it is zero. Agreement at every point is
`exact-finite`: exact, but only at those points.

## Limits and special cases

`limit_case(label, expr, var, point, expected, dir=None)` takes the limit
with SymPy and compares it with `expected`:

- `point` may be finite, `dc.oo` or `-dc.oo`;
- `dir="+"` or `"-"` for a one-sided limit; two-sided otherwise (both sides
  must agree);
- a limit SymPy cannot take is `inconclusive`.

A limit checks one case of a formula, never the formula: its verdict is
`limit-only`. Its mutants show how much it sees.

**A limit of 0 (or ∞) is blind to factors.** Δφ = k g T² → 0 as T → 0 is
equally true of 2 k g T² or k g T³: no mutant of the expression changes
the limit, so the check is `vacuous`. Check the leading behavior instead:
`limit_case("…", phase / T**2, T, 0, k * g)`.

Special cases worth checking for a Gaussian beam: w(0) = w₀;
w(z_R) = √2 w₀; w(z)/z → λ/(π w₀) as z → ∞; R(z) → ∞ as z → 0⁺; the
Gouy phase → ±π/2 as z → ±∞. For an interferometer phase: Δφ/T² → k g
as T → 0, and the sign under g → −g.

Not supported in v0: a limit in several variables, where the order of the
limits matters. State the order in the `.tex` and take the limits one
after the other, each as its own labeled step.

## Mutants

After a check passes, the helper re-runs it on generated mutants of the
claimed expression (mutation set `m0.1`): ×2, the sign of a term, i → −i,
an exponent ±1, s → s² for a dimensional symbol, a dropped term, and a
swap of two symbols of the same dimension. For a `step`, both sides are
mutated; for a limit and a dimension check, the expression; for a series,
the approximation.

- A mutant the check rejects is **killed**. The output prints
  kills/total.
- A mutant equal to the original by value is **equivalent** and not
  counted.
- The rest **survive** and are listed: a person judges whether the check
  should have caught them.
- **No kills: vacuous.** A FAIL on the unmutated check voids the mutants.

Mutation counts measure whether a check *can* fail. A check of the wrong
relation kills its mutants perfectly: mutants say nothing about whether
the checked expression is the one in the `.tex`.
