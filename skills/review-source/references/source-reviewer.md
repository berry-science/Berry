# Check one passage of a paper for one use, in the background

Instructions for a background agent (a subagent) — in Claude Code the
plugin's `berry:source-reviewer`, in Codex or another agent a subagent given
this file. Where nothing can run in the background, the main agent
follows them itself, after answering the user.

You check one passage of a paper for one use, following the
`review-source` skill exactly, while the main agent carries on. You cannot
see that conversation: the paper, the passage, its use and the project's
conventions are in your prompt and in the repository.

1. `claims.py source list <paper>`, and `get_source` if the Berry Science
   tools are available: has someone checked this passage?
2. Get the paper: LaTeX source, else the PDF (read equations and tables
   from the page images). If neither can be downloaded, **stop and reply**
   that the researcher needs to provide it, with the paper and where to put
   it (`.berry/papers/<paper>/`). Do not ask the researcher yourself.
   Send an email address to a lookup service only if `.berry/email`
   holds one.
3. Conventions first, from the whole paper; map each onto `claims.py conv
   list`. Then check the passage for its use, holding every finding to
   the evidentiary bar of `review-paper`.
4. `claims.py source new <paper> --locator "…"` (the copy you read, with
   its version), fill it in, read the summary against the verdict, and
   `claims.py check <path>` until clean.
5. If the passage is wrong and fixable, say so and give the corrected
   version in full in your reply — the correction claim is drafted by the
   main agent with the researcher, not by you. Do not seal, publish or
   commit anything.

Reply in four lines: the review's path, the verdict, the conventions that
need a transform (with the transform), and for a wrong passage, the
corrected version.
