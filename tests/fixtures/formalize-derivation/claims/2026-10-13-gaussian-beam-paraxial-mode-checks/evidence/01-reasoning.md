The fundamental Gaussian beam, written as u = (1/q) exp(−ik r²/(2q)) with
q = z + i z_R, is the textbook trial solution of the paraxial wave equation.
This claim records that each step of that textbook derivation was checked
by an executable script, and how strongly.

- The derivation is `02-derivation.tex`. Every step that carries a claim has
  a `\label{step:…}`.
- The check is `03-code.py`. It states each step in SymPy and hands every
  comparison to the formalize-derivation helper, which alone writes
  verdicts. Its dependencies are pinned inline and locked in
  `03-code.py.lock`.
- `04-output.txt` is the run's output, verbatim (kept here in full; the
  Library limit is 16 000 characters). `05-output.txt` is its
  human-readable part, the lines a reader needs: each step as written in
  the .tex beside the expression that was checked, the verdict, the
  assumptions the verdict needed and the mutants it killed.

What the verdicts say, and what they do not:

- The paraxial equation, 1/q = 1/R − iλ/(πw²), the split of the exponent
  into the 1/e² radius and the wavefront curvature, and the Gouy prefactor
  i z_R/q = (w₀/w) e^{i arctan(z/z_R)} are **proved-symbolic**: SymPy
  reduced the difference of the two sides to zero. The Gouy step needed
  the declared positivity of z, w₀ and λ.
- The waist radius and the far-field divergence are **limit-only**: one
  special case each, not the formula for w(z). The waist limit kills only
  5 of 12 mutants; it cannot see changes to w(z) that vanish at z = 0.
- The near-waist expansion is **series-verified** to order z³: the first
  neglected term is −w₀ z⁴/(8 z_R⁴), and the error shrinks like z⁴.
- The curvature phase k r²/(2R) is **dims-only**: dimensionless, which says
  nothing about factors of 2 or π.
- `step:mode` defines the trial field and is not checked.

A check verifies the expressions in the script. Whether those are the
expressions in the .tex is for a reader to compare, line by line, in
`05-output.txt`.

The two exported results (`06-data.json`, `07-data.json`) are in format
version 0, which may still change. This claim stays a draft.
