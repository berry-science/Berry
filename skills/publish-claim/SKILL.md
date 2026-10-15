---
name: publish-claim
description: Publish claims to the Berry Science Library, private by default — from the project's ledger (claims/), or straight from the conversation in a chat window (Claude.ai, ChatGPT), where publishing is how a finding is recorded. Use when the user asks to publish, share or upload a finding to berry.science, and in a chat window whenever a finding is recorded.
---

# Publish a claim to Berry Science

**In a chat window?** If you are not running inside the user's research
repository — you cannot run commands on their machine or read their files,
as in Claude.ai or ChatGPT — stop here and follow
[references/chat.md](references/chat.md) instead. It publishes straight
from the conversation, without a ledger.

A claim is recorded first, in the project's ledger (skill `record-claim`),
and published from there. The ledger stays the record; the Library copy is
for sharing, review and citation by others. If the finding is not in the
ledger yet, record and seal it with `record-claim` first.

The script is the one `record-claim` uses:

```bash
python3 <base directory of the record-claim skill>/scripts/claims.py <command>
```

It is in `../record-claim/scripts/` from this skill's base directory.

## Before you start

You need the Berry Science MCP server, `https://api.berry.science/mcp`, with
its `publish_claim` tool. If the tool is not available, tell the user to add
the server and sign in with their berry.science account, then stop:

- Claude Code: `claude mcp add --transport http berry https://api.berry.science/mcp`
- Codex: `codex mcp add berry --url https://api.berry.science/mcp`
- Claude.ai, ChatGPT: a custom connector with that URL and OAuth (see
  `clients/chat/README.md` in the skills repository)

Recording and checking claims do not need it: an unpublished claim stays in
the ledger and can be published later. Never publish a claim anywhere else
instead.

## How

1. **Check it.** `claims.py check <id>` must pass with no errors, and the
   claim must be sealed. Answer its warnings before going on: a number not
   found in the evidence, an unpushed commit. Every commit cited must be
   pushed, or its link leads nowhere.

2. **Find the order.** `claims.py order <id>` lists the claim and every
   claim it rests on that is not in the Library yet, cited ones first —
   and, as `sources/…json` paths, the source reviews its citations name,
   each after the correction claim it points to. A
   claim's citations to other ledger claims become links to their Library
   copies, so those are published first. If the user wants only this one
   published, its local citations have to be dropped — say what would be
   lost and ask.

3. **Show it.** Uploads are permanent: there is no edit and no delete. For
   each claim in the order, show the user the title, statement,
   `holds_when`, citations and the evidence list, and say where it goes
   (private, unless they said otherwise). Wait for their go-ahead.

4. **Upload, one claim at a time, in order:**
   - `claims.py payload <id>` prints the `publish_claim` arguments: the
     evidence files inlined, ledger citations turned into Library ids,
     `private: true`, and the anchor `ledger:<id>`. Use
     `--space-id <id>` only when the user named a team space for this
     claim, and `--public` only when they said to publish it publicly.
   - Call `publish_claim` with exactly that JSON. Do not edit it; if
     something in it is wrong, the claim is wrong — see *Rules*.
   - `claims.py published <id> <library id> --visibility <private|public>`
     records the reply's id in the ledger.
   - A `sources/…json` entry is a source review (skill `review-source`):
     `claims.py source payload <path>` → the `review_source` tool →
     `claims.py source published <path> <id> --visibility …`. Ask where it
     goes, recommending public: it is attached to a published paper, and
     the next person using that paper is who it is for.

   The claim's conventions go with it in full (`conventions` in the
   payload), and a paper's citation carries its `locator` and the Library
   id of its source review — that is why the review is published first.

5. **Commit** the updated `claim.json` and source review files, and
   `claims.py index` to show the Library links in `claims/README.md`.

## Large evidence files

The Library takes 16 000 characters per evidence item. A larger file is
marked `"local_only": true` when the claim is recorded, with an excerpt
beside it; `payload` leaves local-only items out, and the full file stays
in the ledger. If a sealed claim has a large file that is not marked,
`payload` refuses it: since the claim cannot change, record a new claim that
`extends` it with the file marked and an excerpt added, and publish that.

## Rules

- **Private by default.** A private claim is visible only to the user,
  signed in; only they can make it public, on the website. Publish publicly
  or into a team space only when the user says so for this claim.
- **Publish what was sealed.** The Library copy must say what the ledger
  says. A wrong claim is answered by a new claim (`refutes` or `extends`),
  recorded and then published — never by editing the payload.
- **One claim per call.** Several findings are several claims.

## After uploading

- Check the reply's `visibility`. It must be `"private"` unless the user
  asked otherwise. If it isn't, or the field is missing, stop before
  publishing anything else and ask the user to check the claim on
  berry.science.
- Tell the user each claim's Library id and link
  (`https://berry.science/library/<id>`), that it is private and
  unreviewed, and that they can make it public from their library on
  berry.science.
