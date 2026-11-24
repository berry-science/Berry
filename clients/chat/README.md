# Berry in a chat interface

For researchers who work in Claude.ai, ChatGPT or a similar chat: the
assistant proposes code, you run it on your own machine or server, and you
paste the results back. Nothing about that changes. When a result is
established, the assistant records it as a **claim** — the finding, the
output you pasted, the code you ran, and what it builds on — and publishes
it to the [Berry Science Library](https://berry.science/library), private
unless you say otherwise. Later claims cite earlier ones, so the Library
keeps the chain of how a result was reached.

## How it behaves

- **It asks you once** per conversation where claims go — your private
  library, or a team and one of its labbooks (a labbook is one topic or
  project) — and whether to publish as you go. You can write the answer
  into the Project's instructions so it is never asked (see below).
- With that yes, it publishes each finding when it is established and tells
  you in one line, with the link. No confirmation per claim.
- Before publishing it checks the draft: the Library's `check_claim_draft`
  (numbers that are in none of the evidence, earlier claims it should
  cite), then a second read of the draft against the evidence alone. A
  chat has no background reviewer, so this check is weaker than in a
  coding agent; a draft that still fails it is not published, and you are
  told why.
- It asks once whether you ran exactly the code it proposed; if not, paste
  the version you ran.
- A claim is never edited. If one turns out wrong, the assistant files a
  correction on it.

Compared with working in a repository with a coding agent: no git commit
for the code (it is attached in full, marked as uncommitted) and no local
copy of the claims — they live on berry.science.

## What it needs

- A chat interface that can **read the procedures** — uploaded **skills**,
  or files in a **Project** — and **connect to a remote MCP server** with
  OAuth sign-in, with tools that write (`publish_claim`). Without writing
  you can still read and check claims.
- A **berry.science account**. berry.science is in a pilot: ask for one at
  [berry.science/pilot](https://berry.science/pilot).

| | Procedures | Connector |
|---|---|---|
| **Claude.ai** | Skills (needs *Code execution and file creation* on), or a Project | Custom connector, on all plans (Free: one custom connector) |
| **ChatGPT** | A Project | Custom connector in *Developer mode*; which plans allow tools that write has changed during 2026 — your first claim will show |

## Get the files

From the [latest release](https://github.com/berry-science/berry/releases/latest):
one zip per skill, and `berry-chat-project.zip`, which unpacks to
`project/`. Or build them in a copy of this repository with
`bash clients/chat/bundle.sh`, which writes `dist/chat/`:

- `skills/*.zip`, one per skill: claims, recall, check-claims,
  review-source, conventions, labbook;
- `project/project-instructions.md` and `project/upload/`, for a Project.

## Set up in Claude.ai

1. **Skills.** Under *Settings → Capabilities*, turn on **Code execution
   and file creation**. Under *Customize → Skills*, choose **+ → Create
   skill → Upload a skill** and upload `claims.zip`, then each other zip.
   (Or use a Project, as for ChatGPT below.)
2. **Connector.** Under *Customize → Connectors*, choose **+ Add → Add
   custom connector**: name *Berry Science*, URL
   `https://api.berry.science/mcp`. Connect, sign in with your
   berry.science account, allow the application. Enable it in the chat
   (the tools menu below the message box). On a Team or Enterprise plan an
   owner adds the connector for the organization first.

## Set up in ChatGPT

1. **Project.** Create one (or use the one you work in). Paste
   `project/project-instructions.md` into its **instructions**, below any
   you have, and add the files in `project/upload/` to its **files**.
2. **Connector.** Turn on **Developer mode** under *Settings → Apps &
   Connectors → Advanced*. Create a connector: name *Berry Science*, URL
   `https://api.berry.science/mcp`, authentication **OAuth**. Sign in,
   allow the application, and enable it in a chat in the Project.

**Say where claims go, once.** In a Project, replace the last line of the
instructions, for example:

    Where claims go: team "Optics group", labbook "Pendulum integrators"; publish as you go, private.

or `Where claims go: my private library; publish as you go.` Then the
assistant does not ask.

## Check the setup

Ask: *"Use Berry Science to list my spaces."* It should name your private
library and any teams you are in.

## Use

- Work as usual. Say *"record this as a claim"* any time; *"document
  today's work"* records the day's findings as claims, one labbook step
  each.
- At the start of a conversation the assistant reads your claims' titles;
  when you ask whether something was done before, or a result contradicts
  an earlier one, it searches them and answers with the claim.
- *"Check claim `<id>`"* reads a claim and what it rests on and reports what
  does not hold up.
- A value or equation from a paper: the assistant checks that passage first
  (attach the PDF if it asks) and files the check under the paper, where
  others using it see it.
- Each claim becomes a step in the topic's **labbook** on berry.science: the
  project step by step, as a PDF.
- Your claims are at [berry.science/library/mine](https://berry.science/library/mine);
  only you can make a private one public, there.

## If something does not work

- **The connector cannot be added, or sign-in fails:** tell the Berry
  Science team what the interface showed.
- **The assistant cannot call `publish_claim`:** your plan may not allow
  tools that write, or the connector is not enabled in this chat.
- **A number in a claim is not in what you pasted:** say so. The assistant
  files a correction; the claim itself stays as published.
- Menu names move from time to time; look for *Skills*, *Connectors* or
  *Developer mode* in the settings.
