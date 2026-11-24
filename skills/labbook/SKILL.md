---
name: labbook
description: Keep the project's labbook — one step per claim, in the researcher's own words, as a LaTeX document rebuilt to PDF (labbook/) and, when the project publishes into a Library labbook, as a step there too. Use after a claim is sealed and published (the first one creates the labbook), when the researcher asks for the labbook or an account of the project, and when a `[labbook]` hook note reports a missing step, a step without a claim, or a failed build.
---

# The labbook

The ledger (`claims/`) is the record a machine checks. The labbook is the same
project for a person: the steps in the order they were taken, why each came
next, what it established, what is still open — readable by someone who was
not there, and written so the researcher can walk anyone through it.

**In a chat window**, follow [references/chat.md](references/chat.md): the
labbook lives on berry.science and is kept with the MCP tools.

## Hard rules

- **A step is a claim.** Every numbered `\section` of `labbook.tex` shows one
  claim with `\claimbox{<id>}`; `labbook.py check` fails otherwise. No step
  without a claim. Findings go in as claims (skill `claims`), never as prose.
- **Everything that states a result is generated** from the ledger: box,
  figures, papers checked, conventions. Never copy a claim's title, statement,
  numbers or figure into the prose; never redraw a figure. If prose and ledger
  disagree, the prose is wrong.
- **Notes** (`\section*{Notes}`, commented out in the template) hold only what
  the researcher asks to have written down beyond the claims, once those
  findings are claims. Tell them these are notes, not claims.
- **History stays.** A step that turned out wrong keeps its place, with a
  sentence pointing to the step that answered it.

## When

After a claim is sealed — and published, when the project publishes (the
checker does both; skill `claims`) — start `labbook-writer` in the background
with the claim id(s) (Claude Code: `berry:labbook-writer`; elsewhere a
subagent given [references/labbook-writer.md](references/labbook-writer.md))
and carry on. Where nothing runs in the background, follow that file yourself
after answering. Never interrupt the researcher for it.

**The first sealed claim creates the labbook**, without asking:
`labbook.py init --title "<the project's question, in a few words>" --lang
<en|de>` in the language of the researcher's messages, then fill
`labbook/voice.md` from their own messages (language, register, their words,
a few sentences of theirs quoted; don't ask them to check it). The author is
`git config user.name`; `--author` only for a name the researcher stated.
Tell them in one line where the PDF is.

**In a Library labbook too.** If `claims.py where` shows a labbook, the step
also goes there with the Berry MCP server's `add_labbook_step` — only the
step's prose; the Library adds the claim box and builds its own PDF. The local
`labbook/` and its PDF stay as they are.

## Where things are

`labbook/` sits beside the project's `claims/` — at the top of the repository,
or in the project's own folder when one repository holds several (the scripts
and the hook use the nearest ledger above; `--root <project folder>` names
it). Commit `labbook.tex`, `voice.md`, `berry-labbook.sty`, `claims.gen.tex`
with your next commit; never the PDF, `build/` or `figures/` unless asked.

`scripts/labbook.py` (`-h` for all): `init`, `gen` (claims.gen.tex and
figures from the ledger), `build` (gen, then LuaLaTeX → `labbook/labbook.pdf`),
`check` (unknown names, steps without a claim, sealed claims not yet shown).
In `labbook.tex`: `\claimbox{<id>}`, `\claimfigures{<id>}`,
`\claimfigure{<id>}{<n>}`, `\sourcebox{sources/….json}`, `\claimref{<id>}`,
`\berryoverview`, `\berryconventions`.

With the plugin, a hook rebuilds the PDF after edits to `claims/` or
`labbook/` and after `claims.py seal|published|index|conv|source`; it speaks
(`[labbook] …`) only when the build failed or sealed claims lack a step.
Without it, run `labbook.py build` yourself. Needs LuaLaTeX (TeX Live,
MacTeX); figures need `vl-convert-python`, fetched through `uv` if missing.

## Building where the researcher looks

- **The researcher's PDF is in the main checkout.** A build in a git worktree
  makes a PDF nobody opens: once the step is merged, run `labbook.py --root
  <the project folder in the main checkout> build` (`git worktree list`, first
  line).
- **A failed build is reported plainly**: that it failed, LaTeX's error line,
  and that the previous PDF is still there. Fix what is yours — math in a
  `\section` title breaks it; write the title in words. A missing TeX package
  is the researcher's to install (`tlmgr install <package>`): say which, and
  don't work around it by editing `berry-labbook.sty`.
