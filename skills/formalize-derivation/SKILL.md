---
name: formalize-derivation
description: Give a derivation in a claim an executable check — each labeled step of the LaTeX derivation restated in SymPy and judged by a helper that alone writes verdicts (proved-symbolic, series-verified, numeric-consistent, limit-only, dims-only, FAIL, vacuous …), tests itself with generated mutants, and exports the result as data a later derivation can build on. Use whenever a claim rests on an analytic derivation, a formula worked out in the session, an approximation or expansion, a limit or special case, or a dimension check, and when the user asks to check, double-check, verify, formalize or "sympy" a derivation — "check my derivation", "check my notes", "is this right?", "verify this result" — or to log or record a result they derived.
---

# Formalize a derivation

A derivation in a claim is prose and LaTeX: a reader has to redo it to trust
it. This skill gives it an **executable check**. Each step of the
derivation is restated in SymPy in a short script, and every comparison is
handed to a helper, `derivcheck`, which writes the verdicts. The script,
its verbatim output and the result go into the claim's evidence beside the
`.tex`, so anyone can re-run the check — and the Berry Science Library
can, later, with its own copy of the helper.

**In a chat window?** The helper needs a shell and Python in the
research repository. Without them — as in Claude.ai or ChatGPT — record
the derivation as a `derivation` evidence item (publish-claim's
`references/chat.md`) and say plainly in the reasoning that it has no
executable check. A computation in the chat's own code tool is not this
skill's check: report what it showed, never "verified".

**A derivation without a check is a warning, not an error.** Write one
whenever the derivation carries the claim: it is the strongest evidence a
derivation can have short of a formal proof, and the cheapest to re-run.

What a check can and cannot say:

- It can make it **certain that the script checked these expressions,
  under these assumptions, by this method, and that the check could
  fail** (the mutants show it).
- It makes it **cheap to see** whether those expressions are the ones in
  the `.tex`: the output prints each step as written beside each step as
  checked.
- It **cannot** make it certain that they are. That comparison is a
  reader's, and the claim should not read as more than what was checked.

Scripts here assume SymPy's model of the mathematics. Numeric agreement is
never reported as proved, and a check that cannot fail is reported as
`vacuous`, never as a pass.

## The evidence

In the claim's `evidence/`, numbered in reading order (see record-claim's
[claim-format.md](../record-claim/references/claim-format.md)):

| File | `kind` | What |
|---|---|---|
| `02-derivation.tex` | `derivation`, format `latex` | The derivation. Each step that can be checked carries `\label{step:…}`. |
| `03-code.py` | `code`, language `python` | The check script, with its dependencies inline (PEP 723). |
| `03-code.py.lock` | `code`, language `toml` | The lockfile, where uv is available. |
| `04-output.txt` | `output` | The run's output, verbatim. Over 16 000 characters: `"local_only": true`, plus an excerpt (its human-readable lines) as its own `output` item. |
| `NN-data.json` | `data`, format `json` | Each exported result. |
| `*.as-written.*` | `derivation`, `code`, `output` | Where the derivation as found had a step that failed: its `.tex`, script and output, each captioned `As written: …` (step 3). |

`claims.py check` (skill record-claim) runs this skill's coverage check on
every claim with a `derivation` item.

## How

The helper and the runner are in this skill's `scripts/`. Run the runner
from the repository root, by claim id, with the skill's absolute base
directory — **one command, no `cd`, no shell variables**:

```bash
python3 <this skill's base directory>/scripts/formalize.py run <claim-id>
```

It finds the claim's check script in `claims/<claim-id>/evidence/` and
writes the output there. The path forms (`run evidence/03-code.py --out …`)
still work.

1. **Label the derivation.** In the `.tex`, give each step a label:
   `\label{step:inverse-q}`, one per equation or per `align` row. A step
   that is a definition, or an argument in words, gets a label too: it is
   then left out honestly, below.

2. **Write the check script** next to it, `evidence/03-code.py`:

   ```python
   # /// script
   # requires-python = ">=3.10"
   # dependencies = ["sympy==1.14.0", "mpmath==1.3.0", "pint==0.24.4"]
   # ///
   import derivcheck as dc

   dc.begin(tex="02-derivation.tex", seed=20261013)

   z = dc.symbol("z", "z", dim="length", positive=True)
   w0 = dc.symbol("w0", "w_0", dim="length", positive=True, convention="beam-radius-1e2@1")
   lam = dc.symbol("lam", r"\lambda", dim="length", positive=True)
   zR = dc.pi * w0**2 / lam
   q = z + dc.I * zR
   w = w0 * dc.sqrt(1 + (z / zR) ** 2)
   R = z * (1 + (zR / z) ** 2)

   dc.unchecked("step:mode", "definition", "the trial field")
   dc.step("step:inverse-q", 1 / q, 1 / R - dc.I * lam / (dc.pi * w**2))
   dc.limit_case("step:waist", w, z, 0, w0)
   dc.series_step("step:near-waist", w, w0 * (1 + z**2 / (2 * zR**2)), z, 3)
   dc.export("inverse_q", "step:inverse-q")
   dc.finish()
   ```

   - **Declare every symbol once**, with its LaTeX, dimension, assumptions
     and — where a convention fixes its meaning — the convention
     `key@version` from `claims/conventions.json` (skill conventions).
     Assume only what the `.tex` assumes: every verdict prints the
     assumptions it needed.
   - **Write each step in SymPy by hand.** The helper parses no LaTeX:
     the LaTeX parsers tested on beam notation either failed or, worse,
     silently produced a different expression. Write ∇² and ∂ in explicit
     coordinates.
   - **Build on checked steps**, not on copies: `dc.result("step:a")`
     returns step a's checked expression (so does the value `dc.step`
     returns); pass `uses=["step:a"]`. The helper also records the uses it
     finds in an expression, and flags a declared use whose expression
     does not occur — the mark of a re-typed link.
   - **One call per step**, with the step's label:

     | Call | Checks | Best verdict |
     |---|---|---|
     | `step(label, lhs, rhs, computed=None)` | lhs = rhs exactly (`computed="lhs"` marks a side the script computes, if the helper cannot see it) | `proved-symbolic` |
     | `series_step(label, exact, approx, var, order, point=0)` | exact = approx + O(t^(order+1)) | `series-verified` |
     | `limit_case(label, expr, var, point, expected, dir=None)` | a special case or limit (`point` may be `dc.oo`; `dir` '+' or '-') | `limit-only` |
     | `dims(label, expr, "length/time")` | the dimension, and dimensionless arguments of exp, log, trig, Bessel | `dims-only` |
     | `unchecked(label, reason_code, note)` | nothing, said out loud | `unchecked` |

     `reason_code` is `definition`, `from-source`, `beyond-backend`,
     `prose` or `deferred`. Every `step` also checks the dimensions of
     both sides when the symbols have them.

     **A step that introduces an approximation is not `unchecked`.** Check
     it with `series_step` (or a `limit_case`) against the exact quantity
     it approximates, when that quantity can be written down. `unchecked`
     is for definitions, quoted results and arguments in words. The helper
     raises an alarm when an `unchecked` note reads like an approximation.
   - **`export(name, "step:…", regime=…)`** for each result another
     derivation might build on; `regime={"small": z/zR, "order": 3}` for
     an approximation.
   - **`finish()`** last: it writes the summary and sets the exit code.

3. **Run the check on the derivation as you found it**, before changing
   anything:

   ```bash
   python3 <this skill's base directory>/scripts/formalize.py run <claim-id> --as-written
   ```

   This copies the `.tex` and the script to `*.as-written.*` beside them
   and writes this run's output there too. If a step fails, that output
   is evidence of what was wrong: keep all three as their own evidence
   items, each with a caption that starts `As written:` (the runner
   prints the entries to add), and say in the reasoning which step failed
   and why, and how the error was found: by this FAIL, or by reading
   before the check ran. Then fix the `.tex`, then the script, and run
   again (step 4).
   The claim's result rests on the second run; the as-written run counts
   toward nothing the claim states. If no step fails and nothing needs
   fixing, delete the three copies and go on to step 4.

4. **Run it** through the runner, which puts the helper on the path and
   uses `uv run` with the script's pinned dependencies where uv exists:

   ```bash
   python3 <this skill's base directory>/scripts/formalize.py run <claim-id>
   ```

   It writes `04-output.txt` after `03-code.py` (or the output item the
   claim already lists) and prints the evidence entry to add.

   Without uv: `python3 -m pip install sympy mpmath pint` first.

5. **Read the output.** For each step it prints the verdict, the step as
   written in the `.tex`, the step as checked (`sympy.latex`), the symbols
   with their assumptions, the assumptions the proof needed, the
   denominators it treated as nonzero, whether the step still holds
   outside the declared domain, and how many generated mutants the check
   caught.
   - **FAIL**, with its residual: the step is wrong — or the script is.
     If this is the first run on the derivation as you found it, keep it
     as written (step 3) before anything else. Then **fix the `.tex`, then
     the script; never only the script.** A check that passes on a
     corrected expression while the `.tex` keeps the wrong one hides the
     error it found. Say what was fixed in the reasoning.
   - **vacuous**: the check cannot fail — an expression compared with
     itself, an `O()` term that swallows the claim, or no mutant caught.
     Strengthen it (for a limit of 0, check the leading coefficient).
   - **inconclusive**: SymPy could not decide. Say so; try another form,
     or a numeric or special-case check; or mark the step `unchecked`.
   - **Survivors**: mutants the check did not catch. Judge whether it
     should have. A limit or a dimension check has survivors by nature.
   - **Compare "as written" with "as checked"** for every step. The
     check proves the second; the claim is about the first.

6. **Export and lock:**

   ```bash
   python3 <this skill's base directory>/scripts/formalize.py export <claim-id> inverse_q
   python3 <this skill's base directory>/scripts/formalize.py lock <claim-id>
   ```

   `export` writes the next free `NN-data.json` (or replaces the item that
   already holds that result) and prints its entry; `lock` writes
   `03-code.py.lock` (needs uv). One command each, no `cd`, no shell
   variables.

7. **List the files** in `claim.json` (table above), then
   `claims.py check <id>` (skill record-claim). It runs the coverage
   check: errors for a FAIL or vacuous step, a step label in the output
   that the `.tex` does not have, a verdict line the helper did not
   write, a lint violation in the script, an output from another version
   of the script or `.tex`, an export that differs from what the helper
   wrote. Warnings for a `.tex` label nothing checked, inconclusive and
   unchecked steps, weak checks, alarms, and a result not exported. Fix
   the errors; answer the warnings. `formalize.py cover <claim-id>` runs
   the same check for one claim.
   A FAIL in an output captioned `As written:` is not an error: it is
   what that output is kept for. A claim with only an as-written run, or
   whose unmarked output has a FAIL, does not pass.

8. **Say no more than was checked.** The statement may say "proved",
   "verified" or "exact" only if every step on the way to the result is
   at least `numeric-consistent`; `check` refuses it otherwise. Put the
   verdicts in the reasoning: which steps are proved, which are limit
   cases only, which are unchecked.

   **Say how a problem was found** — in your reply to the user and in the
   reasoning file alike: by the check (quote its FAIL line), or by
   reading. Do not write "the check found" without a FAIL line to quote.

9. **Keep the claim a draft.** The export format is `format_version 0`
   and may still change; `check` refuses to pass a sealed claim with a v0
   export. It freezes at v1. Tell the user why in one line: "Left as a
   draft: its exported result uses format version 0, which may still
   change, so it is not sealed."

## Verdicts, strongest first

| Verdict | Means |
|---|---|
| `proved-symbolic` | SymPy reduced lhs − rhs to exactly zero (method and needed assumptions printed) |
| `series-verified` | every term up to the stated order agrees; the error shrinks as stated; next term printed |
| `exact-finite` | exact algebraic evaluation agrees at random rational points |
| `numeric-consistent` | agreement at random points to 30 digits; never proof |
| `limit-only` | one limit or special case agrees: says nothing about the rest |
| `dims-only` | the dimensions agree: blind to ½, 2π and signs |
| `inconclusive` | SymPy could not decide either way |
| `unchecked` | left out, with the reason |
| `vacuous` | the check cannot fail — an error |
| `FAIL` | the two sides differ; the residual is printed — an error |

## Rules

- **Only the helper judges.** The linter rejects a script that prints its
  own PASS/FAIL, wraps a helper call in `try`, asserts a constant,
  compares with `==`, compares floats without a tolerance, substitutes
  numbers before the check, patches the helper, or exits on its own.
- **Never edit the output.** Its verdict lines are hash-chained per run;
  an edited, added or copied line is an error. Re-run instead.
- **A red run is not evidence.** `formalize.py run --against subs.json`
  re-runs steps against substitute expressions (for graders, and to see a
  check fail); its output is refused as evidence.
- **Re-run after any change** to the `.tex` or the script: the output
  records both files' hashes.
- **No parsed LaTeX, no strings for expressions.** A string is accepted
  only as the label of an earlier step.

## References

- [references/sympy-identities.md](references/sympy-identities.md):
  identity checking in SymPy and its pitfalls, and what the helper does
  about each.
- [references/numeric-and-limits.md](references/numeric-and-limits.md):
  numeric, exact-point and limit checks.
- [references/units-and-dimensions.md](references/units-and-dimensions.md):
  declaring dimensions; what `dims` and pint check.
- [references/approximations.md](references/approximations.md):
  `series_step`, `O()` terms, regimes.
- [references/formats.md](references/formats.md): the output lines, the
  export record and `--against`, for anyone reading or grading a run.

A worked example — a textbook Gaussian-beam derivation as a draft claim —
is in this repository's `tests/fixtures/formalize-derivation/`.
