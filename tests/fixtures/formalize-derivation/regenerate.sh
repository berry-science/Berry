#!/bin/sh
# Re-run the worked example's check and rebuild its derived evidence files.
# Run after changing the helper; review the diff of 04-output.txt before committing.
set -e
here=$(cd "$(dirname "$0")" && pwd)
scripts="$here/../../../skills/formalize-derivation/scripts"
id=2026-10-13-gaussian-beam-paraxial-mode-checks
ev="$here/claims/$id/evidence"
python3 "$scripts/formalize.py" --root "$here/claims" run "$id" > /dev/null
grep -v '^{' "$ev/04-output.txt" > "$ev/05-output.txt"
python3 "$scripts/formalize.py" --root "$here/claims" export "$id" inverse_q
python3 "$scripts/formalize.py" --root "$here/claims" export "$id" w_near_waist
python3 "$here/../../../skills/claims/scripts/claims.py" --root "$here/claims" check
