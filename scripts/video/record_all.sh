#!/usr/bin/env bash
# Full recording run: every beat, from a clean Firestore state, with each step's
# stdout/stderr captured to docs/video/logs/ so the run can be audited after.
#
# Usage: bash scripts/video/record_all.sh

set -u

export PATH="/c/ffmpeg/bin:/c/Users/kesha/AppData/Local/Google/Cloud SDK/google-cloud-sdk/bin:$PATH"
export GOOGLE_CLOUD_PROJECT=diligence-room-live
export DILIGENCE_FIRESTORE_DATABASE=diligence-asia
export MSYS_NO_PATHCONV=1

REPO=/d/dr
LOGS="$REPO/docs/video/logs"
DASH="https://diligence-room-dashboard-378831539922.asia-south1.run.app"
PS1_EXE="powershell -NoProfile -ExecutionPolicy Bypass -File"

rm -rf "$LOGS"
mkdir -p "$LOGS"
cd "$REPO" || exit 1

step() {
  local name="$1"; shift
  local log="$LOGS/$name.log"
  echo "=== [$name] START $(date -u +%H:%M:%S) ===" | tee -a "$log"
  "$@" >>"$log" 2>&1
  local rc=$?
  echo "=== [$name] EXIT $rc at $(date -u +%H:%M:%S) ===" | tee -a "$log"
  echo "$name $rc" >> "$LOGS/_exitcodes.txt"
  return $rc
}

echo "--- full reset: deal + registry ---"
step 01-reset-all      uv run python scripts/video/reset_deal.py --deal-id deal-falcon --with-registry --confirm
step 02-seed-registry  uv run python registry/seed.py --project diligence-room-live --confirm-live
curl -s --max-time 30 "$DASH/api/findings" > "$LOGS/03-findings-before.json" 2>&1
echo "findings before replay: $(cat "$LOGS/03-findings-before.json")"

echo "--- beats 2+3: one continuous split-screen take ---"
step 04-beat23 $PS1_EXE "D:/dr/scripts/video/record_beat3.ps1" -OutName "beat23_take1.mkv" -Seconds 80

curl -s --max-time 30 "$DASH/api/findings" > "$LOGS/05-findings-after.json" 2>&1

echo "--- populated dashboard beats ---"
step 06-beat0 $PS1_EXE "D:/dr/scripts/video/record_view.ps1" -Beat 0 -Route "/findings" -Seconds 36 -Take 3
step 07-beat1 $PS1_EXE "D:/dr/scripts/video/record_view.ps1" -Beat 1 -Route "/registry" -Seconds 30 -Take 2 -Scroll
step 08-beat4 $PS1_EXE "D:/dr/scripts/video/record_view.ps1" -Beat 4 -Route "/findings/f4c993d48cda" -Seconds 44 -Take 3 -Scroll -ScrollEvery 8
step 09-beat5 $PS1_EXE "D:/dr/scripts/video/record_view.ps1" -Beat 5 -Route "/security" -Seconds 30 -Take 2 -Scroll

echo "--- beat 6 needs a registry without v2.5 already published ---"
step 10-reset-registry uv run python scripts/video/reset_deal.py --with-registry --confirm
step 11-seed-registry  uv run python registry/seed.py --project diligence-room-live --confirm-live
step 12-beat6 $PS1_EXE "D:/dr/scripts/video/record_beat6.ps1" -Take 6 -Seconds 29

echo "--- beat 7 needs an unapproved draft ---"
step 13-reset-drafts uv run python scripts/video/reset_deal.py --deal-id deal-falcon --drafts-only --confirm
step 14-beat7 $PS1_EXE "D:/dr/scripts/video/record_beat7.ps1" -Take 2 -Seconds 30

echo "--- assemble ---"
step 15-build uv run python scripts/video/build_final.py

echo
echo "=== TAKE DURATIONS ==="
for f in beat23_take1 beat0_take3 beat1_take2 beat4_take3 beat5_take2 beat6_take6 beat7_take2; do
  p="docs/video/takes/$f.mkv"
  if [ -f "$p" ]; then
    printf '%-18s %s s\n' "$f" "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$p")"
  else
    printf '%-18s MISSING\n' "$f"
  fi
done | tee "$LOGS/_durations.txt"

echo
echo "=== EXIT CODES ==="
cat "$LOGS/_exitcodes.txt"
