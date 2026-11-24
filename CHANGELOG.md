# Changelog

What changed in each release of Berry, for the people using it. Each
section's text is also the release's notes on GitHub.

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
