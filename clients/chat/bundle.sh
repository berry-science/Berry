#!/usr/bin/env bash
# Assemble the files for using the claim skills in a chat interface, in
# dist/chat/:
#
#   bash clients/chat/bundle.sh
#
#   skills/    one zip per skill with a chat procedure — to upload as
#              skills (Claude.ai). Each zip has the skill's folder at its root.
#   project/   instructions and the chat procedures as files for a Project
#              (ChatGPT, or a Claude Project instead of skills).
#
# Copies, never edits: the skills stay the one source. The Project's files
# are the skills' own references/chat.md, renamed because a Project's files
# need distinct names.
set -euo pipefail

repo="$(cd "$(dirname "$0")/../.." && pwd)"
out="$repo/dist/chat"
rm -rf "$out"
mkdir -p "$out/skills" "$out/project/upload"

# The skills that work in a chat: each routes to its references/chat.md.
skills="claims recall check-claims review-source conventions labbook"

for skill in $skills; do
  (cd "$repo/skills" && zip -qr "$out/skills/$skill.zip" "$skill" -x "*/__pycache__/*" "*.pyc")
  cp "$repo/skills/$skill/references/chat.md" "$out/project/upload/berry-$skill-chat.md"
done
cp "$repo/clients/chat/project-instructions.md" "$out/project/project-instructions.md"

cat <<EOF
$out/
  skills/*.zip                       upload as skills (Claude.ai)
  project/project-instructions.md    paste into a Project's instructions
  project/upload/                    add these files to the Project
EOF
