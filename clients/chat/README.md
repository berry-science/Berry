# Using the claim skills in a chat interface

For researchers who work in a chat interface — Claude.ai, ChatGPT, or a
similar one: the assistant proposes code, you run it on your own machine or
server, and you paste the results back. Nothing about that changes. When a
result settles something, the assistant offers to record it as a
**claim** — the finding, the output you pasted, the code you ran, and what
it builds on — and publishes it, privately, to the
[Berry Science Library](https://berry.science/library). Later claims cite
earlier ones, so the Library keeps the chain of how a result was reached.

The one thing the assistant will ask you when recording: whether you ran
exactly the code it proposed. If you changed it, paste the version you ran.

What this does not have, compared with working in a repository (the
`record-claim` skill): no git commit for the code — the code is attached in
full instead, and the claim says it was not under version control — and no
local copy of the claims. They live on berry.science.

## What it needs

Any chat interface works that can do two things:

- **Read the procedures**, either as uploaded **skills** or as files in a
  **Project** with instructions.
- **Connect to a remote MCP server** with OAuth sign-in, and let the
  assistant use a tool that writes (`publish_claim`). Without that you can
  still check claims, but not publish them.

And a **berry.science account**. berry.science is in a pilot: reach out
to us at [berry.science/pilot](https://berry.science/pilot) to get one.

| | Procedures | Connector |
|---|---|---|
| **Claude.ai** | Skills (needs *Code execution and file creation* on), or a Project | Custom connector, on all plans (Free: one custom connector) |
| **ChatGPT** | A Project | Custom connector in *Developer mode*; which plans allow it, and tools that write, has changed during 2026 — your first claim will show |

## Get the files

In a copy of this repository:

```bash
bash clients/chat/bundle.sh
```

This writes `dist/chat/`:

- `skills/*.zip`, one per skill, to upload as skills: research-monitoring,
  recall, publish-claim, check-claims, review-source, conventions, labbook;
- `project/project-instructions.md` and `project/upload/` with their chat
  procedures, for a Project.

## Set up in Claude.ai

**1. The skills.** Under *Settings → Capabilities*, make sure **Code
execution and file creation** is on. Then under *Customize → Skills*,
choose **+ → Create skill → Upload a skill**, and upload
`publish-claim.zip`; then the same for each of the other zips. The skills
notice that they are running in a chat and follow their chat procedure.

Instead of skills you can use a Claude **Project**: set it up as described
for ChatGPT below, with the Project's instructions and files.

**2. The connector.** Under *Customize → Connectors*, choose **+ Add → Add
custom connector**: name *Berry Science*, URL
`https://api.berry.science/mcp`. Connect it, sign in with your
berry.science account, and allow the application on the page that asks.
Then enable it in the chat (the tools menu below the message box).

On a Team or Enterprise plan, an owner adds the connector for the
organization first; then you connect to it.

## Set up in ChatGPT

**1. The Project.** Create one, for example *"Research"*, or use the
Project you already work in:

- Paste `project/project-instructions.md` into the Project's
  **instructions** (below instructions you already have).
- Add the files in `project/upload/` to the Project's **files**.

**2. The connector.** Turn on **Developer mode** under *Settings → Apps &
Connectors → Advanced*. Create a connector: name *Berry Science*, URL
`https://api.berry.science/mcp`, authentication **OAuth**. Sign in with
your berry.science account and allow the application on the page that
asks. Then enable the connector in a chat in the Project.

## Check the setup

In a chat, ask: *"Use Berry Science to list my claims."* It should answer,
with none yet.

## Use

- Work as usual. When a result settles something, the assistant offers to
  record it — or say *"record this as a claim"*. It shows you the claim
  first and publishes only when you agree.
- Your claims are the assistant's memory of the project. At the start of
  a conversation it reads their titles; when you ask whether something was
  already checked, when a result might contradict an earlier one, or when
  it is about to rely on a fact, it searches them — by meaning, not only by
  wording — and answers with the claim.
- *"Check claim `<id>`"* reads a claim and everything it rests on from
  berry.science and reports what does not hold up.
- When a result takes a value or an equation from a paper, the assistant
  checks that passage first — attach the PDF if it asks — and files the
  check under the paper on berry.science, where others using the paper see
  it. The conventions your numbers are written in travel with each claim.
- Each claim also becomes a step in your project's **labbook** on
  berry.science: the project, step by step, as a PDF you can read and
  share there — written in your own words, kept up to date as you go.
- Your claims are at
  [berry.science/library/mine](https://berry.science/library/mine), private
  to you until you make one public there.

## If something does not work

- **The connector cannot be added, or signing in fails:** tell the Berry
  Science team what the interface showed.
- **The assistant says it cannot call `publish_claim`:** your plan may not
  allow tools that write, or the connector is not enabled in this chat.
- **A number in a claim is not in what you pasted:** say so before agreeing
  to publish. Published claims cannot be edited; a wrong one is answered by
  a new claim that cites it.
- Menu names in both interfaces move from time to time. If a step does not
  match what you see, look for *Skills*, *Connectors* or *Developer mode*
  in the settings.
