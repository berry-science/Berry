# When a result is a claim

A result is a claim when all four hold:

1. **It could be false**: a statement with the number, comparison or yes/no
   that makes it checkable. *"Explicit Euler at dt = 0.05 drifts 4 % in
   energy over 10⁴ periods"* could be false; *"RK4 looks better"* could not.
2. **It was produced here, and its output still exists**: a run, derivation
   or measurement in this project, with its output on disk. Not a
   recollection, a summary of a paper, or what is well known.
3. **Its conditions can be named**: the system, parameter ranges, code
   version, what was held fixed, and whether it is a simulation, a model or
   a measurement.
4. **Something builds on it**: the next step uses it as an input, a
   baseline or a reason to change direction, or the researcher treats it as
   settled. Record it before anything rests on it.

**Negative results count** (an approach that failed, under stated
conditions), and so do calibrations, methods shown to work, and corrections
of a paper's passage (skill `review-source`).

**Not yet:** a run about to be repeated with other parameters; a surprising
number seen once; a plan or hypothesis (labbook open points); a test
passing or a plot drawn, unless the plot shows something that could be false.

**A further check is not a reason to wait.** If the result stands under the
conditions already run, record it with those in `holds_when`; a later check
that changes it becomes a claim that `extends` or `refutes` it.

Two findings in one run are two claims; the second can cite the first.
