# Formats: the output, the export, red runs

For anyone reading or grading a run: a reviewer, an evaluation harness, a
server re-running the check. **Format version 0: it may still change, and
no claim is sealed with it.**

## The output

A run prints, among whatever the script prints itself:

```
[dc:3f9a2c1b0d4e] step:inverse-q  proved-symbolic  via cancel
[dc:3f9a2c1b0d4e]   as written: \frac{1}{q(z)} &= \frac{1}{R(z)} - \frac{i \lambda}{\pi w(z)^2} ,
[dc:3f9a2c1b0d4e]   as checked: \frac{1}{z + \frac{i \pi w_0^{2}}{\lambda}} = …
{"check":"step","derivcheck":"check","label":"step:inverse-q","mac":"…","run":"3f9a2c1b0d4e","seq":2,"verdict":"proved-symbolic",…}
```

- **Lines for people** start with `[dc:<run nonce>]`.
- **Machine lines** are one JSON object per line with a `derivcheck` key:
  `header` (first: Python, SymPy, mpmath, pint, helper, linter and
  mutation-set versions; the helper's, script's and `.tex`'s SHA-256; the
  seed, precision and points; `runner`; `against`), then one `check` per
  check call, an `export` per exported result, and a `summary` last
  (per-label verdict, failed and vacuous labels, alarms, notes, the step
  to export if nothing was (`unexported`), the symbol table, the exit
  code).
- A `check` line's `uses` lists the earlier steps it rests on: those the
  script declared, and those the helper found in its expressions
  (`uses_inferred`).
- Each machine line carries `run` (the nonce), `seq` (0, 1, 2 …) and
  `mac`: the first 16 hex digits of SHA-256 over
  `nonce|previous mac|the line's canonical JSON without mac` (keys sorted,
  no spaces, UTF-8). `derivfmt.RunOutput` verifies the chain, and flags
  lines with verdict words that the helper did not write.

The chain is **tamper-evidence, not security**: the helper is open source,
so a determined forger can compute it. Only a re-run with a trusted copy of
the helper settles a dispute.

**Exit code:** 0, or 1 on any `FAIL` or `vacuous` verdict. A run that
never reaches `finish()` has no summary line; `formalize.py run` then
exits non-zero (3 if the script itself exited 0).

**Comparing two runs:** `formalize.py compare a.txt b.txt` compares the
machine lines with the nonce, the macs and the timings left out. A
faithful re-run in the same environment compares equal; the header shows
any difference of environment.

## The derivation as it was found

When the check is first run on a derivation as it was found and a step
fails, that run is kept as evidence of the error, beside the corrected
derivation and its run. The marker is the item's **caption**: it starts
with `As written:` (compared without case). It is a caption, not an extra
key, because `claims.py payload` publishes an item's kind, content,
format, language and caption, and nothing else.

```json
{"kind": "derivation", "file": "evidence/02-derivation.as-written.tex", "format": "latex",
 "caption": "As written: the derivation as it was found, before any correction."},
{"kind": "code", "file": "evidence/03-code.as-written.py", "language": "python",
 "caption": "As written: the check of the derivation as it was found."},
{"kind": "output", "file": "evidence/04-output.as-written.txt",
 "caption": "As written: its output, verbatim."}
```

`formalize.py run <claim-id> --as-written` (or `run <script> --as-written`)
makes the three files and prints these entries. In the coverage check:

- an as-written output must come from a script and a `.tex` in the claim
  (matched by content hash), and must pass the hash chain, as any output;
- its `FAIL` lines are not errors; they are reported, as what the output is
  kept for. A `FAIL` on a step of the as-written output is the record that
  **the check found the defect**;
- it counts toward no verdict, export, coverage or statement of the claim;
- the claim still needs an unmarked output of the corrected derivation;
  without one, or with a `FAIL` in it, the claim does not pass.

The copied script names the original `.tex` file (`dc.begin(tex=…)`): to
re-run it, put the as-written `.tex` under that name in a scratch folder.

## The exported result

`formalize.py export <claim-id> <name>` (or `export <output> <name> <file>`)
writes the `export` record:

```json
{
  "format_version": 0,
  "result": "w_near_waist",
  "expr": "Mul(Symbol('w0', positive=True), Add(…))",
  "latex": "w_0 \\left(\\frac{\\lambda^{2} z^{2}}{2 \\pi^{2} w_0^{4}} + 1\\right)",
  "symbols": {"w0": {"name": "w0", "latex": "w_0", "kind": "scalar", "assumptions": ["positive"],
                     "dim": "length", "convention": "beam-radius-1e2@1"}, …},
  "regime": {"small": ["Mul(…)"], "small_latex": ["\\frac{\\lambda z}{\\pi w_0^{2}}"], "order": "3", "point": "0"},
  "verdict": "series-verified",
  "path": {"step:near-waist": "series-verified"},
  "step": "step:near-waist",
  "backend": "sympy",
  "backend_version": "1.14.0",
  "helper": "0.1.0"
}
```

- `expr` is SymPy's `srepr`: exact, and SymPy-specific
  (`sympy.sympify(expr)` reads it back with its assumptions).
- `verdict` is the weakest verdict on `path`, the steps the result rests
  on through `uses`, declared or found in the expressions.
- `regime` is `null` for an exact result.
- `backend` leaves room for a formal backend; the verdict scale reserves
  `formal` above `proved-symbolic`.

## Red runs: `--against`

```bash
formalize.py run <claim-id> --against subs.json --out red.txt
```

A red run by claim id writes only where `--out` says, never over the
claim's output.

`subs.json` maps step labels to substitute expressions, as SymPy source
(`"r**2 + r*w + w**2"`) or `srepr`:

```json
{"step:inverse-q": "1/(z - I*pi*w0**2/lam)"}
```

For a `step` the substitute replaces the right-hand side; for a
`series_step`, the approximation; for a `limit_case` or `dims`, the
expression. To substitute an exported result, use its `step`. The header
records the substitutes, the affected lines carry `"against": true`, and
mutants are not run on them. The coverage check refuses such an output as
evidence. The environment variable `DERIVCHECK_AGAINST=<file>` does the
same without the runner.
