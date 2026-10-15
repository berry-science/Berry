# Identity checking in SymPy, and its pitfalls

`step(label, lhs, rhs)` checks lhs = rhs. Each pitfall below was
reproduced with SymPy 1.14.0; next to it is what the helper does about it.

## Reaching zero proves; not reaching it proves nothing

Deciding whether an expression is zero is undecidable in general. So
`simplify(lhs - rhs) == 0` is one-sided: zero is a proof, anything else is
silence.

- **`==` is structural.** `(x + 1)**2 == x**2 + 2*x + 1` is `False`. The
  linter rejects `==` in a check script; the helper compares differences.
- **`simplify` gives up.** With `z`, `z_R` positive, `simplify` does not
  reduce exp(−i·atan(z/z_R)) − (1 − iz/z_R)/√(1 + z²/z_R²) to zero.
- **`.equals()` can return `None`** — for that same expression — and decides
  numerically inside. The linter rejects it in scripts.

The helper's cascade: the difference as it stands, then `expand`,
`cancel`, `together`, `powsimp`, `trigsimp`, `expand_complex`, `simplify`,
each with a time limit (10 s by default, `begin(timeout=…)`). The first to
reach exactly zero is the method printed. If none does with the declared
assumptions, it tries again with every assumption dropped (an identity
over all complex values holds on any subset). Then exact evaluation at
rational points for algebraic expressions (`exact-finite`), then the
numeric check (`numeric-consistent`); otherwise `inconclusive`. Before any
of this, a numeric check at random points runs: if the two sides differ
there, confirmed at twice the precision, the step is a `FAIL` with its
residual, and no symbolic route can overrule that.

## Assumptions cut both ways

- **They enable proofs.** `log(x*y) = log(x) + log(y)` is proved with `x`,
  `y` positive and false otherwise (at x = y = −1 the sides differ by 2πi).
- **They can block them**: the Gouy expression above simplifies with no
  assumptions and not with positive ones.
- **They act before any check.** With `x` positive, `sqrt(x**2)` *is* `x`
  the moment it is built; nothing downstream can see that positivity was
  used.

So each verdict prints the assumptions declared, and for a proof those it
**needed**: the helper drops each symbol's assumptions in turn and reports
the ones without which SymPy no longer reached zero in the time limit
(needed, or SymPy was too slow without them — it cannot tell). It also
evaluates the step at one point that breaks every declared assumption and
says whether the step still holds there: "no — the declared assumptions
carry this step" is the line to read.

Declare only what the `.tex` assumes. `positive=True` on a symbol that can
be negative makes wrong steps pass.

## Evaluation before the check

SymPy evaluates as it builds. `x/x` is `1` at once: the condition x ≠ 0 is
gone before the helper sees the step (the Physics Derivation Graph's
objection to CAS-checked derivations). The helper cannot recover it. What
it does:

- it prints every denominator left in the step that is not provably
  nonzero: "treated as nonzero: y − 1";
- when the two sides are already identical as built and neither side is
  computed, it raises an alarm: one side may be a copy of the other, or
  evaluation may have used an assumption (`sqrt(x**2)` → `x`). A side counts
  as computed when it contains an earlier step's result, is a matrix, is
  marked with `step(…, computed="lhs")`, or its source — followed back
  through the script's assignments — does more than write symbols,
  constants and elementary functions down (`diff`, a matrix product, a
  function of the script). So `L*P` for ABCD matrices or `diff(u, r)`
  against its typed result raise no alarm; `a*b` against `b*a` does;
- it calls a step `vacuous` when the script passes the same expression as
  both sides (read from the script's source, since SymPy's cache makes
  equal expressions the same object).

## Branch cuts

`sqrt`, `log`, `atan` and fractional powers take principal branches.
`sqrt(1/s)` and `1/sqrt(s)` differ on the negative real axis;
`log(exp(I*x)) − I*x` is −2πi at x = 4. The helper prints a note for each
principal branch whose argument is not provably on the safe side, and for
a symbol with no assumptions puts one sample point on the negative real
axis, so `sqrt(1/s) = 1/sqrt(s)` fails.

## Non-commuting operators

Ordinary symbols commute: `(A + B)**2` expands to `A**2 + 2*A*B + B**2`.
Declare operators with `kind="operator"`. **`expand_complex` and
`simplify` silently treat non-commuting symbols as commuting** and reduce
`(A+B)**2 − (A**2 + 2*A*B + B**2)` to zero; the helper uses only order-
preserving rewrites (`expand`) for such expressions. Numerically, it puts
random 3×3 complex matrices in for the operators: agreement means the step
holds in general; disagreement means it holds at most given relations
between the operators — commutators the table does not declare — and is
reported `inconclusive`, never `FAIL`. Commutation relations cannot be
declared in v0.

## Piecewise at special points

Correct identities can come out unequal at a special point. The geometric
sum `summation(q**k, (k, 0, n-1))` is `Piecewise((n, Eq(q, 1)), ((1 - q**n)/(1 - q), True))`;
its difference from `(1 - q**n)/(1 - q)` simplifies to
`Piecewise((nan, Eq(q, 1)), (0, True))`, and `.equals(0)` returns `False`.
The helper does not read a Piecewise residual as a failure: it falls
through to the numeric check (`numeric-consistent` here), prints the
denominators it assumed nonzero (1 − q), and prints a Piecewise residual
with its branches when it stays inconclusive.

## Stray symbols

A symbol named `e`, `i`, `pi`, `d`, `dx`, `partial` or `nabla` is almost
always a constant or a differential typed as a symbol, or LaTeX debris.
The helper refuses them as names, and fails a step whose free symbols are
not all in the symbol table, or are a table symbol rebuilt with other
assumptions. Use `dc.E`, `dc.I`, `dc.pi`; name a distance `ell` or `L`.
