# /// script
# requires-python = ">=3.10"
# dependencies = ["sympy==1.14.0", "mpmath==1.3.0", "pint==0.24.4"]
# ///
"""Check of 02-derivation.tex: the fundamental Gaussian beam.

Run it with the skill's runner, which puts the helper on the path:
    python3 <formalize-derivation>/scripts/formalize.py run 03-code.py --out 04-output.txt
"""
import derivcheck as dc

dc.begin(tex="02-derivation.tex", seed=20261013)

# The symbol table, declared once.
r = dc.symbol("r", "r", dim="length", nonnegative=True)
z = dc.symbol("z", "z", dim="length", positive=True)
w0 = dc.symbol("w0", "w_0", dim="length", positive=True, convention="beam-radius-1e2@1")
lam = dc.symbol("lam", r"\lambda", dim="length", positive=True)

k = 2 * dc.pi / lam
zR = dc.pi * w0**2 / lam
q = z + dc.I * zR
w = w0 * dc.sqrt(1 + (z / zR) ** 2)
R = z * (1 + (zR / z) ** 2)
u = 1 / q * dc.exp(-dc.I * k * r**2 / (2 * q))

dc.unchecked("step:mode", "definition", "the trial field: the fundamental Gaussian mode")

laplacian = dc.diff(r * dc.diff(u, r), r) / r
dc.step("step:paraxial", laplacian - 2 * dc.I * k * dc.diff(u, z), 0)

dc.step("step:inverse-q", 1 / q, 1 / R - dc.I * lam / (dc.pi * w**2))
inverse_q = dc.result("step:inverse-q")
dc.step("step:exponent", -dc.I * k / 2 * inverse_q, -1 / w**2 - dc.I * k / (2 * R), uses=["step:inverse-q"])

dc.dims("step:phase-dims", k * r**2 / (2 * R), "1")

dc.step("step:gouy", dc.I * zR / q, w0 / w * dc.exp(dc.I * dc.atan(z / zR)))

dc.limit_case("step:waist", w, z, 0, w0)
dc.limit_case("step:divergence", w / z, z, dc.oo, lam / (dc.pi * w0))

dc.series_step("step:near-waist", w, w0 * (1 + z**2 / (2 * zR**2)), z, 3)

dc.export("inverse_q", "step:inverse-q")
dc.export("w_near_waist", "step:near-waist", regime={"small": z / zR, "order": 3})
dc.finish()
