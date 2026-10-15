---
name: labbook
description: Keep the project's labbook: a LaTeX document, rebuilt as PDF, with one step per sealed claim, in the researcher's own words. Use after every sealed claim (the first one creates it), when the user asks for a labbook or an account of the project, and when the labbook hook reports a missing step or a step without a claim.
---

# The labbook

The ledger (`claims/`) is the record a machine can check. The labbook is
the same project for a person: the steps in the order they were taken, why
each came next, what it established, and what is still open — readable from
start to finish, step by step, by someone who was not there.

**In a chat window?** Follow [references/chat.md](references/chat.md):
there the labbook lives on berry.science, one step per claim, and
berry.science renders the PDF. The same holds in a repository whose claims
are published, when the researcher wants the labbook on berry.science
(to read it there, or to share it with their team): the steps go to the
Library as in chat mode, in the space the claims are in, and the link to
give the researcher is `page_url`.

**A step is a claim.** Each numbered section of `labbook.tex` shows a
claim with `\claimbox`; `labbook.py check` fails on one that does not,
and the hook says so. The labbook is not where notes from the session, a
summary or a chapter about a phase go: those findings are claims, recorded
first. What is not a finding goes, briefly, into where things stand, the
open points, or the notes (below).

## What it is made of

```
labbook/
├── labbook.tex        the steps, written by you, in the researcher's voice   committed
├── voice.md           how the researcher writes                              committed
├── berry-labbook.sty  the look                                               committed
├── claims.gen.tex     claim boxes, figures, papers, conventions — generated  committed
├── figures/           the claims' Vega-Lite figures, as PDF                  not committed
└── build/, labbook.pdf                                                       not committed
```

Everything here is local: no account and no connection to berry.science
are needed. Links to the Library appear in the boxes only for claims that
were published.

The script is `scripts/labbook.py` in this skill (it reads the ledger with
`record-claim`'s `claims.py`):

| Command | |
|---|---|
| `init --title "…" [--author "…"] [--lang en\|de]` | Create `labbook/`, with `.gitignore` so only the sources are committed |
| `gen` | Write `claims.gen.tex` from the ledger, render the figures |
| `build` | `gen`, then LuaLaTeX → `labbook/labbook.pdf` |
| `check` | What `labbook.tex` names that does not exist, and sealed claims it does not show yet |

**Everything that states a result is generated.** You never copy a
claim's title, statement, numbers or figure into `labbook.tex`; you place
it:

| In labbook.tex | Shows |
|---|---|
| `\claimbox{<id>}` | The claim: title, statement, holds-when, conventions, what it rests on (with the verdict of each paper checked), sealed or draft, links to the ledger and to the Library |
| `\claimfigures{<id>}` / `\claimfigure{<id>}{<n>}` | Its figures / evidence item n |
| `\sourcebox{sources/…json}` | A paper checked: the passage, the verdict, the summary |
| `\claimref{<id>}` | A link to a claim shown elsewhere |
| `\berryoverview`, `\berryconventions` | The list of claims; the conventions with every version and why it changed |

So the labbook cannot say something the ledger does not, and a claim
re-published or a review added shows up without touching the prose.

## Automatic PDF

With the `berry` plugin installed (Claude Code or Codex), a hook rebuilds the PDF in the
background after every edit to `labbook/` or `claims/` and after every
`claims.py seal`, `published`, `index`, `conv` or `source` command. It is
silent when the build works. You hear from it on your next turn only when
LaTeX failed (fix `labbook.tex` — the previous PDF stays in place) or when
a claim was sealed that the labbook does not show yet.

Without the plugin, run `labbook.py build` yourself after each change.
It needs a TeX distribution with LuaLaTeX (TeX Live, MacTeX); figures need
`vl-convert-python`, which `labbook.py` fetches through `uv` if it is not
installed.

## Figures

A claim's figure is its Vega-Lite spec, which the Library draws on the web
and `labbook.py gen` renders to PDF for the labbook. Never redraw a claim's
figure for the labbook: it must show what the claim shows.

## After every claim

**The first sealed claim creates the labbook.** If `labbook/` does not
exist when a claim is sealed, create it then, without asking — with the
title and language from the first claim's setup message (skill
`record-claim`), or your proposal if they did not answer: `labbook.py
init --title "<the project's question, in a few words>" --lang <en|de>`,
in the language of the researcher's messages, and fill `labbook/voice.md`
from their messages. The author is `git config user.name`; give `--author`
only for a name the researcher stated — never a guess. With the
plugin, the labbook hook says so when a claim is sealed and there is no
labbook. Tell the researcher in one line where the PDF is.

Every sealed claim gets its step. This is the moment to do it — and it
runs beside the work, not in place of it: start a background agent with
[references/labbook-writer.md](references/labbook-writer.md) as its
instructions (in Claude Code: `berry:labbook-writer`) and the claim id(s),
or write the step yourself if the researcher is waiting for nothing else.

**A step** is a `\section` whose title says what the step found, then:

1. **Why this step**: the question it answered, and why it came next —
   what the previous step left open. One short paragraph.
2. **What was done**: the method in plain words, what was held fixed, and
   any paper it rests on (`\sourcebox` for the passage checked).
3. `\claimbox{<id>}` and `\claimfigures{<id>}`.
4. **What it means**: for the question, and for the next step. Say plainly
   when a step was a dead end; negative results are steps.

Then update the top and the end:

- **Where things stand** (`\section*{Stand}` / `Where things stand`):
  rewrite its three or four sentences.
- **Open points and follow-up questions** — after the steps, before any
  notes, never removed: what is not settled, what to try next, the questions to
  discuss. Strike nothing silently: an answered question moves into the
  step that answered it.

- **Notes** (`\section*{Notes}` / `Notizen`, commented out in the
  template, after the open points): only what the researcher explicitly
  asks to have written down beyond the claims — context, decisions,
  remarks. Written after the findings it touches are recorded as claims,
  never in place of one; tell the researcher these are notes, not claims.

A step's three paragraphs are a few sentences each: the box carries the
claim.

Finish with `labbook.py check` (no errors; every step shows a claim; every
sealed claim shown). Commit `labbook/` — `labbook.tex`, `voice.md`,
`claims.gen.tex` — with the claim when you wrote the step yourself; a
step written in the background is committed with your next commit. Never
commit the PDF or `figures/` unless the researcher asks.

## The researcher's voice

The labbook is theirs. Write it as they write, so they can walk
anyone through it without rephrasing:

- **`labbook/voice.md` first.** Read it before writing a step. When it is
  still the template, fill it in from the researcher's own messages in
  this conversation: the language they write in, their register (*wir*,
  short sentences, or formal), their words for the system, the methods and
  the quantities, and two to five sentences of theirs quoted verbatim. Do
  not ask them to check it. Update it when you learn more.
- The same language as the researcher's messages — `init --lang de` for
  German headings and box labels; English otherwise.
- Their terms, not yours: if they say *Residuum*, the labbook says
  *Residuum*. No agent vocabulary (*claim ledger*, *evidence item*,
  *seal*) in the prose; the boxes carry that.
- Plain and precise. No hedging, no praise, no *"successfully"*. Numbers
  only from the claims.

## Rules

- **The ledger is the truth.** If the labbook and a claim disagree, the
  labbook is wrong: fix the prose.
- **Drafts may appear**, marked as drafts by their box, while the
  researcher discusses them; a step built on a draft says so.
- **Do not rewrite history.** A step that turned out wrong stays, with a
  sentence pointing to the step that corrected it.
