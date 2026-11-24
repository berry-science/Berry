---
name: record-claim
description: Record a result or a dead end as a claim in the project's ledger (claims/): a checkable statement with its evidence, the code and everything it builds on. Use when a result, method, calibration or negative result is established, before anything builds on it, and when the user asks to record, document or write up findings for Berry.
---

# Record a finding as a claim

**In a chat window?** The ledger needs the research repository: a shell to
run `claims.py` and git. If you are not running inside it — as in
Claude.ai or ChatGPT, where the user runs the code elsewhere and pastes
results back — record the finding by publishing it directly instead:
follow `references/chat.md` in the publish-claim skill.

Research done with an agent moves fast, and what it rests on gets lost: a
number computed three hours ago, the version of the code that produced it,
the paper a formula came from, the run that failed. The ledger keeps that
record as it happens, one finding at a time.

A **claim** is one finding: a statement that could be false, the conditions
it holds under, and the evidence behind it. Claims cite what they build on —
earlier claims, papers, data, the code commit — so the ledger is a graph,
and any result can be traced back step by step to the evidence it rests on.
Each claim is small enough to check on its own.

The ledger is a `claims/` folder in the research repository, committed with
the code. It needs no account and no network. A claim in it has the shape
of a [Berry Science](https://berry.science) Library claim, so it can be
published later without rewriting (skill `publish-claim`).

All commands below are one script, run from anywhere inside the repository:

```bash
python3 <this skill's base directory>/scripts/claims.py <command>
```

`claims.py -h` lists the commands. The format of `claim.json` and the
evidence files is in [references/claim-format.md](references/claim-format.md);
read it before writing your first claim.

## When to record

When a finding is established — a result, a method shown to work, a
calibration, an approach that failed — and before anything builds on it;
and when the user asks. The test is research-monitoring's
`references/claim-threshold.md`. With the `berry` plugin a hook notices
runs and a background agent drafts the claim (skill
`research-monitoring`); `claims.py pending` lists the drafts waiting for
the user.

## How

1. **Settle the evidence first.** Every number in the claim comes from one
   run of one version of the code. Commit the files that run used — only
   those, never other work in progress — and ask the user before pushing:
   the commit's link leads nowhere until it is pushed, which publishing
   needs (skill `publish-claim`). If the code changed after the run, run
   it again. If a number is surprising, check it with more data first. If
   the code cannot be committed, put the relevant code in an evidence item
   and set `"uncommitted": true` in `provenance`.

2. **Start the claim.** `claims.py new "<title>" --type result` creates
   `claims/<id>/` with `claim.json` and an empty `evidence/01-reasoning.md`,
   and prints the id. The id starts with today's date. When recording a
   finding after the fact, give the date the finding was made — the day of
   the run, from the output or the commit — with `--date YYYY-MM-DD`.

3. **Write the evidence files** into `claims/<id>/evidence/`, numbered in
   reading order, and list each in `claim.json` (see the format reference):
   - `01-reasoning.md`: why the statement follows from the material — what
     was computed, compared or measured, and why the result is believed.
     Refer to citations as [1], [2] in the order of `citations`.
   - Then the material: the figure as a Vega-Lite spec with its data inline,
     the run's output **verbatim**, the parameters, a derivation, the data as
     CSV, the relevant code excerpt. Copy output, never retype it.
     If the claim rests on a derivation, give it an executable check with
     the formalize-derivation skill.

4. **Write the claim** in `claim.json`: `title`, `statement`, `claim_type`,
   `holds_when`, `conventions` (the versions its numbers are written in,
   as `"key@version"` from `claims.py conv list` — skill `conventions`),
   `contributors` (yourself first, with your exact model id as
   your system prompt gives it — never a guess), `anchors`,
   `provenance` with the repository, full `commit` hash and the `command`
   that was run. See *Writing the claim*.

5. **Cite everything it rests on**, each with a relation and a one-sentence
   reason:
   - earlier claims in the ledger it uses: `{"local": "<id>", "relation": "uses"}`;
   - the code: the https URL of the commit, relation `uses`;
   - papers, datasets and outside results: `doi:…`, `arxiv:…` or a URL. A
     paper the claim **uses** something from gets the passage, `"locator":
     "Eq. (12)"`, and the source review that checked it, `"review":
     "sources/…json"` (skill `review-source`) — or, for a standard
     reference value (CODATA, NIST, a textbook constant), `"standard":
     true` instead of a review. If the passage was wrong,
     the claim also cites the corrected version with `uses`. A value from a
     paper is converted to the project's conventions first, and the
     reasoning shows the conversion;
   - a claim it corrects: relation `refutes`; one it refines: `extends`.

   Find the earlier claims with the skill `recall` — `claims.py recall`
   with the finding's subject, `--exact` for its key numbers and
   parameters, and the Library's `search` when berry.science is
   connected — not from memory of the session.

   If you used something you cannot cite — a value from memory, an
   assumption — either find its source, record it as its own claim with its
   own evidence, or say it plainly in `holds_when` as an assumption.

6. **Check it:** `claims.py check <id>`. Fix every error. Treat warnings as
   questions to answer: a number in the statement that appears in no
   evidence item, a missing commit, a commit not pushed. Two of them are
   asked of drafts only, and are the ones a claim recorded in a hurry
   skips: *cites no earlier claim, but these share its subject* — cite
   each one it uses, or say in the reasoning why it rests on none — and
   *numbers in the reasoning found in no other evidence item and no cited
   claim* — attach the output, cite where each comes from, or state it as
   an assumption.

   **Push back when the evidence is not there.** If the output a claim
   rests on is gone — only a summary, a recollection, a number mentioned
   in passing — rerun it, or tell the user it cannot be recorded as it
   stands. If it uses an earlier finding that is not recorded, record that
   one first.

7. **Show it, then seal it.** First re-read the draft against what the
   user decided since it was written: a condition they have since
   settled must not still read as open. Show the user the title, statement,
   `holds_when`, what it builds on (the earlier claims it cites, or why
   none) with the other citations, and the evidence list in a few lines. Seal
   when they agree — or right away, if they asked you to record findings
   without stopping: `claims.py seal <id>`. Sealing freezes the claim: its
   fields and evidence files are hashed, and `check` fails if they change.

8. **Update the index and commit:** `claims.py index` rewrites
   `claims/README.md` (the list, a graph of how claims build on each
   other, the conventions and the papers checked). Commit the claim folder
   and the index together — with `conventions.json` and the source reviews
   it cites, if they changed — and check with `git status` that every file
   was committed. Commit `labbook/` too once its step is written; a step
   written in the background is committed with your next commit.

   Research repositories often ignore `*.csv`, `*.txt` or `*.json`, and
   git then leaves those evidence files out without a word. `check` and
   `seal` fail on an evidence file git ignores, naming the rule. Fix it
   once for the whole ledger: add `!claims/**` to that `.gitignore`, after
   the rule — ask the user first (in the setup message, for the first
   claim): it is their repository's file.

9. **The labbook.** Every sealed claim gets its step in the project's
   labbook (skill `labbook`) — in the background (its
   `references/labbook-writer.md`), so the user's work goes on. If there
   is no `labbook/` yet, the first sealed claim creates it, without
   asking (skill `labbook`). The labbook hook reminds you if it is
   missing.

## The first claim of a project: one setup message

When the ledger gets its first claim, put everything a project asks only
once into **one message**, beside the draft, and carry on:

- the conventions its numbers depend on, as you read them from the code
  and the researcher's messages (skill `conventions`) — confirm or
  correct;
- the labbook: its title (the project's question, in a few words) and
  language — it is created when the first claim is sealed (skill
  `labbook`);
- the line `!claims/**` for `.gitignore`, if git ignores an evidence file;
- the PDF or source of a paper the claim uses, if it cannot be downloaded.

One reply settles it. A proposed title and language stand if they do not
answer; a convention you could not read from the code stays out until they
do. The labbook's voice is not asked: write it from their messages.

## Writing the claim

- **One finding per claim.** Two findings are two claims; the second can
  cite the first.
- **The title is the finding, not the topic.** *"RK4 at dt = 0.01
  reproduces the analytic resonance curve to 1e-6"*, not *"Driven
  oscillator simulation"*. Say *Simulated …* or *In a model of …* when it
  is not a measurement.
- **The statement could be false**, and carries the numbers that make it
  checkable. No hedging, and no judgment without its reference point:
  not *negligible* or *dominant*, but the comparison, with the thing
  compared against named and from the same work.
- **It stands outside the session.** No session labels (*round 5*, *the
  handoff*, *run B*) and no plans: a reader who was not there must follow
  it. `check` warns on the common ones.
- **Every number comes from this claim's evidence.** `check` flags numbers
  it cannot find in any evidence file.
- **`holds_when` starts with the kind of evidence** (simulation, model,
  measurement), then the system, the parameter ranges, versions and what
  was held fixed.

## Rules

- **Sealed claims are never edited.** If one turns out wrong, restore it
  (`git checkout`) and record a new claim that cites it with relation
  `refutes`, saying what was wrong. A refinement is a new claim with
  `extends`. The ledger keeps the whole path, including the wrong turns.
- **Drafts are yours to change** until sealed. Delete a draft folder that
  will not become a claim.
- **A sealed claim cites only sealed claims.** Seal what it rests on first.
- **Keep large files in the ledger.** The Library takes 16 000 characters
  per evidence item. Keep a larger log or table in full, mark it
  `"local_only": true`, and add an excerpt beside it as its own item — the
  lines the statement uses — before sealing. Publishing leaves local-only
  items out.
- **Code behind a login.** If the repository needs a login, say so in the
  reasoning: the claim's own code excerpt and output must then stand on
  their own.
- **Nothing leaves the machine.** Recording is local. Publishing is a
  separate step, only when the user asks (skill `publish-claim`).

## Looking back

- `claims.py trace <id>` prints everything a claim rests on, as a tree,
  down to the papers (with the passage and its review's verdict) and
  commits at the bottom. Use it to explain how a
  result was reached, and before relying on an old claim.
- To check claims rather than record them, use the skill `check-claims`.
