# Units and dimensions

Dimension checks are cheap and catch a class of error the algebra does
not: `exp(-r**2/w)` for `exp(-r**2/w**2)`, a curvature phase k r²/(2R) that
is not dimensionless, an interferometer phase that does not come out in
radians. They are **blind to dimensionless factors**: a missing ½, 2π or
sign passes. That is why `dims-only` is the weakest positive verdict.

## Declaring them

Each symbol's `dim` is a string over SI dimensions, read by
`sympy.physics.units`:

```python
dc.symbol("w0", "w_0", dim="length", positive=True)
dc.symbol("g", "g", dim="length/time**2", positive=True)
dc.symbol("k", "k", dim="1/length", positive=True)
dc.symbol("x", "x", dim="1")            # dimensionless
```

Base names: `length`, `mass`, `time`, `current`, `temperature`, `amount`,
`luminosity`; derived ones such as `velocity`, `energy`, `force`,
`frequency`, `action` also work. Angles are dimensionless, as in SI.
A name SymPy does not know is refused. Units from `sympy.physics.units`
(`meter`, `second`) may appear in expressions and carry their dimension.

## What is checked

- **Every `step`**, when all its symbols have dimensions: both sides must
  have the same dimension (0 carries any), sums must add like to like,
  and the arguments of exp, log, trig, hyperbolic and Bessel functions must
  be dimensionless. A mismatch is a `FAIL`.
- **`dims(label, expr, "1")`** checks one expression against a stated
  dimension, with the same rules, and adds a second opinion from **pint**
  where pint is installed: the expression is evaluated with unit-carrying
  random numbers, and pint raises on `exp(1 m)` and on adding meters to
  seconds. The output says whether pint agrees.
- Derivatives divide by the variable's dimension; integrals multiply.
- A matrix (ABCD) is not dimension-checked: its elements carry different
  dimensions.

## Not unyt

unyt adds and multiplies with dimensions, but returns 2.718… for `exp(1 m)`
instead of refusing it (unyt with numpy, checked 2026-10-13). pint raises
`DimensionalityError`. The helper uses SymPy's dimensions symbolically and
pint numerically, never unyt.
