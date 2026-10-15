# When a result is a claim

A result has reached claim level when **all four** hold:

1. **It could be false.** There is a statement someone could check and
   find wrong — with the number, the comparison or the yes/no that makes it
   checkable. *"The residual drops to 0.009 µm with the STA ramp"* could be
   false. *"The STA ramp looks promising"* could not.
2. **This project's work produced it, and its output still exists.** It
   came from a run, a derivation or a measurement done in this project —
   in this session or an earlier one — and its output is on disk or
   pasted. Not a recollection, not a summary of a paper, not what is well
   known.
3. **Its conditions can be named.** You can say what it holds under: the
   system, the parameter ranges, the code version, what was held fixed, and
   whether it is a simulation, a model or a measurement.
4. **Something will build on it.** The next step uses it — as an input, a
   baseline, a reason to change direction — or the researcher treats it as
   settled. This is the trigger: record a result **before** anything rests
   on it, not when the project ends.

Also a claim, and easy to miss:

- **A negative result:** an approach that did not work, under stated
  conditions. *"Explicit Euler drifts by 4 % in energy over 10⁴ periods at
  dt = 0.05"* is a finding.
- **A calibration:** a measured or fitted setting others will reuse.
- **A method shown to work:** a procedure, with the conditions it worked
  under and how that was checked.
- **A correction:** a passage of a paper found wrong and fixed (skill
  `review-source`); the corrected version is its own claim.

Not yet a claim:

- **A run that will be repeated** with other parameters in the next few
  minutes, to find out whether the effect is real. Wait for the run that
  settles it.
- **A surprising number checked once.** Check it with more data first.
- **A plan, an intention, a hypothesis.** Those go in the labbook's open
  points, not in the ledger.
- **A result whose output is gone**, recorded later from a summary or
  from memory. Rerun it, or recover the output first: evidence is the
  output, not a description of it.
- **A test passing, a build working, a plot drawn.** Engineering, not a
  finding — unless the plot shows something that could be false.

**When unsure**, draft it: a draft costs nothing and is deleted if the
researcher disagrees. A missing claim under a result costs the whole chain.

**Two findings in one run** are two claims; the second can cite the first.
