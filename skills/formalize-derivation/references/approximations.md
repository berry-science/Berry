# Approximations

An approximation is not an identity. `series_step` checks one, and its
verdict, `series-verified`, is never reported as `proved-symbolic`. Nor is
an approximation a step to leave `unchecked`: check it against the exact
quantity it approximates whenever that can be written down. The helper
raises an alarm when an `unchecked` note reads like an approximation. Never
check an "≈" step with `step`: the helper raises an alarm when the `.tex`
says ≈ and the check says =, and another when the `.tex` writes an
approximation as = with no O() term.

```python
dc.series_step("step:near-waist", w, w0 * (1 + z**2 / (2 * zR**2)), z, 3)
dc.series_step("step:far-field", w, w0 * z / zR + w0 * zR / (2 * z), z, 2, point=dc.oo)
```

`series_step(label, exact, approx, var, order, point=0, eps=None)` claims

    exact = approx + O(t^(order+1)),   t = var − point   (t = 1/var at point = oo)

so `order` is the highest power of the small parameter that the claim
states correctly.

## What it does

1. **Rejects an O() term that swallows the claim.** SymPy absorbs every
   term an O() covers: `1 + 5*eps + O(eps)` *is* `1 + O(eps)`, and
   `w0*(1 + z**2/(2*zR**2)) + O(z**2)` is `w0 + O(z**2)` — the z² term,
   the whole content of the claim, is gone before anything is compared.
   An O() term at or below the stated order is `vacuous`. Write `approx`
   without O(), or with O() of exactly order + 1; any other order is a
   `FAIL` that says which order to state.
2. **Expands exact − approx** one order beyond the claim and requires every
   coefficient up to the stated order to vanish (by the symbolic cascade,
   or numerically, which makes it `numeric-consistent`). A coefficient
   that does not vanish is a `FAIL`, printed as the term it is:
   `-w0*z**2/(2*zR**2)`.
3. **Prints the first neglected term**: `next term: -w0*z**4/(8*zR**4)`. A
   reader judges the regime from it.
4. **Checks the error scaling numerically**, independently of SymPy's O()
   arithmetic: |exact − approx| at t = ε, ε/2, ε/4 (ε = 1/10, or `eps=`)
   must shrink at least like ε^(order+1). It prints the measured powers.
   Coefficients that agree with an error that does not shrink as stated
   are `inconclusive`.

Mutants of `approx` (a dropped term, a doubled coefficient, a flipped sign
…) must fail the check; none failing makes it `vacuous`.

## Regimes

The small parameter is `var − point`, in the units of `var`. When the
physics says z ≪ z_R, the numeric scaling samples z = 0.1, 0.05, 0.025
against z_R between 0.35 and 2.4: inside the regime, but only roughly.
Choose `eps` when that is not small enough.

The regime travels with an exported result:

```python
dc.export("w_near_waist", "step:near-waist", regime={"small": z / zR, "order": 3})
```

Format version 0 knows a list of small parameters, an order and a point.
Inequalities, and the order in which several limits are taken, are not
encoded yet; say them in the `.tex` and the claim's `holds_when`.

## Not covered in v0

- **Two small parameters at once.** The order of the limits matters and
  SymPy's behavior there was not tested. Expand in one, then the other,
  as separate labeled steps, and say the order.
- **Asymptotic results with no series** (stationary phase, a large-N
  integral). Check them numerically against the exact expression at
  growing parameters in their own steps, and mark the step `unchecked`
  with reason `beyond-backend` if that cannot be done.
