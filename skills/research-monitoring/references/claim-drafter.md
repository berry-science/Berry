# Draft one finding as a claim, in the background

Instructions for a background agent (a subagent) — in Claude Code the
plugin's `berry:claim-drafter`, in Codex or another agent a subagent given
this file. Where nothing can run in the background, the main agent
follows them itself, after answering the user.

You draft a claim in the research repository's ledger, following the
`record-claim` skill exactly, while the main agent carries on with the
researcher. You cannot see that conversation: everything you know is in
your prompt and in the repository.

1. Read `claims/README.md`, `claims.py conv list` and `claims.py pending`,
   so you cite the right earlier claims and conventions and do not draft a
   claim that already exists as a draft. Then look for what the finding
   builds on or contradicts (skill `recall`): `claims.py recall` with its
   subject, `claims.py recall --exact` with its key numbers and parameter
   names. A claim it contradicts is cited with `refutes`, and said in your
   reply.
2. Find the output. Prefer the file the run wrote; otherwise the output
   given verbatim in your prompt. Copy it, never retype it. If there is no
   output to attach, stop and say so — a claim without its output is not
   drafted.
3. `claims.py new "<title>" --type <type>`, then write the evidence files
   and `claim.json` as `record-claim` describes: reasoning first, the
   output verbatim, the figure as Vega-Lite with its data inline if the run
   produced plot data, the parameters — and the code itself, with
   `"uncommitted": true` in `provenance`, if the run's code is not
   committed (a repository without commits too): that never stops a
   draft; citations with relations and
   reasons — earlier claims (`local`), the commit URL, papers with
   `locator` and `review` where a source review exists; `conventions` as
   `key@version`. If the finding rests on a derivation, give it an
   executable check with the `formalize-derivation` skill: its script,
   output and exported result go in the same claim folder.
4. `claims.py check <id>` until it has no errors. Answer the two
   questions it asks of drafts yourself: an earlier claim it may use is
   cited, or the reasoning says why not; a number in the reasoning from
   nowhere is traced to its output or citation, or stated as an
   assumption. Leave the warnings you cannot resolve from the repository
   for the researcher. If the output the claim rests on cannot be found,
   do not draft it — say so.
5. **Do not seal. Do not publish. Do not commit.** Do not change any file
   outside the new claim folder.

Reply in four lines: the claim id, its title, its statement, and what is
still open (each remaining warning, and anything you had to assume).
