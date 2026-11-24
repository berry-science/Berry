# Changelog

What changed in each release of Berry, for the people using it. Each
section's text is also the release's notes on GitHub.

## 0.4.0 — 2026-11-24

Berry gets lighter and publishes on its own: the agent writes each finding
down itself, an independent checker reads it, and a checked claim is sealed
and published to berry.science without asking each time.

### Changed

- One `claims` skill replaces `record-claim`, `publish-claim` and
  `research-monitoring`; the skills an agent reads on the claim path are a
  fraction of their former length, and every other skill is shorter too.
- A claim is written as a short `claim.md` — a header, the reasoning, the
  evidence as paths to files already on disk, the citations — which
  `claims.py` compiles into the ledger. Output is copied, never retyped.
- The main agent writes the claim itself; the background drafter is gone.
- An independent `claim-checker` agent checks each claim, seeing only the
  files: at most two rounds. A pass seals the claim; issues left after the
  second round hold it as a draft for you (`claims.py pending`). Sealing
  without a passing check needs `--without-check`.
- Publishing is asked about once per project, together with where claims go
  (`claims.py where`): your private library, or a team and one of its
  labbooks. After that, checked claims are published as you work, privately
  unless you chose otherwise.
- In chat windows, Berry asks once where claims go, then publishes each
  finding when it is established, after `check_claim_draft` and a re-read.
- `check-claims` is now for audits you ask for; the per-claim check is the
  checker's.

### Added

- `claims.py login`, `logout`, `where` and `publish`: claims and the source
  reviews they cite go to berry.science over HTTP, are read back and compared
  with what was sent, and only then recorded. A retry never makes a second
  copy.
- A repository can hold several projects, each with its own ledger and
  labbook in its folder; `claims.py init` starts one there, and the hooks and
  `formalize.py` find the nearest.
- `claims.py checked`, which records the checker's verdict.
- In a team, claims can be filed in a labbook — one topic of the team — and
  read topic by topic.

### Fixed

- The labbook PDF is rebuilt after publishing, so its Library links appear.
- For a project below the top of the repository, `check`'s `.gitignore`
  advice names the ledger's path, so following it re-includes the files.

## 0.3.1 — 2026-11-24

Fixes from running Berry on real referee work: source reviews name what was
actually read, drafts come earlier and are re-read before sealing, and
`check` catches what the Library would refuse.

### Fixed

- `check` refuses a source review's `source_version` longer than the Library
  takes, warns about a paper's PDF kept in the ledger instead of the
  git-ignored `.berry/papers/`, and warns about session labels ("round 5",
  "handoff") in a draft.
- A source review names the copy actually read, with its version, and its
  summary is read against its verdict before it is filed.
- A researcher's email goes to a lookup service only with their consent.
- A result is proposed as a claim as soon as it stands under the conditions
  run, and a draft is re-read against later decisions before it is sealed.
- After the first claim is published, the labbook is offered on
  berry.science too.
- Library links in the ledger and the labbook follow `BERRY_WEB_URL` when it
  is set, so a test Library's claims link to that Library.

### Added

- The chat skills and `berry-chat-project.zip` can be downloaded from each
  GitHub release, so you no longer have to build them.
- README: signing in to the MCP server from tmux by pasting the callback
  address.
