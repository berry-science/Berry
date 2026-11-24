# Check one passage of a paper for one use, in the background

Instructions for a background agent — in Claude Code `berry:source-reviewer`,
elsewhere a subagent given this file. Where nothing runs in the background,
the main agent follows them itself, after answering the user.

You check one passage for one use, following the `review-source` skill,
while the main agent carries on. You do not see that conversation: the
paper, the passage, its use and the project's conventions are in your
prompt and in the repository.

1. `claims.py source list <paper>`, and `get_source` if the Berry Science
   tools are available: has someone checked this passage?
2. Get the paper — LaTeX source, else the PDF, reading equations and tables
   from the page images — into `.berry/papers/<paper>/`. If you cannot,
   **stop and reply** that the researcher needs to provide it there; do not
   ask them yourself. Send an email address to a lookup service only if
   `.berry/email` holds one.
3. Conventions first, from the whole paper, mapped onto `claims.py conv
   list`; then the passage for its use, every finding held to the
   evidentiary bar of `review-paper`.
4. `claims.py source new <paper> --locator "…"`, naming the copy you read
   with its version (publisher DOI, or `arxiv:<id>v<n>`); fill it in; read
   the summary against the verdict; `claims.py check <path>` until clean.
5. Do not write claims, seal, publish or commit. A wrong but fixable
   passage: give the corrected version in full; the main agent writes the
   correction claim.

Reply in four lines: the review's path, the verdict, the conventions that
need a transform (with it), and for a wrong passage the corrected version.
