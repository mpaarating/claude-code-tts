#!/bin/bash
# On-demand TTS — called by Claude when user says "read that to me"
# Text preprocessing (markdown stripping, pronunciation, truncation)
# is handled server-side. This script just dispatches raw text.
#
# Usage: tts-speak.sh "text to speak"
#    or: echo "text" | tts-speak.sh
#    or: tts-speak.sh --file /path/to/file
#    or: tts-speak.sh --dry-run "text"   # print what would be spoken, no audio
#    or: tts-speak.sh --dry-run --summary "text"   # same, through the auto-speak summarizer

KOKORO_URL="http://127.0.0.1:${KOKORO_PORT:-7723}"

DRY_RUN=0
MODE=""
while [[ "$1" == --dry-run || "$1" == --summary ]]; do
    [[ "$1" == --dry-run ]] && DRY_RUN=1
    [[ "$1" == --summary ]] && MODE="summary"
    shift
done

# Get text from argument, stdin, or file
if [[ "$1" == "--file" && -f "$2" ]]; then
    TEXT=$(cat "$2")
elif [[ -n "$1" ]]; then
    TEXT="$1"
else
    TEXT=$(cat)
fi

[[ -z "$TEXT" ]] && { echo "No text provided"; exit 1; }

# Check daemon is running
if ! curl -s --max-time 2 "$KOKORO_URL/health" >/dev/null 2>&1; then
    echo "Kokoro daemon not running. Start with: launchctl load ~/Library/LaunchAgents/com.$(whoami).kokoro-tts.plist"
    exit 1
fi

if [[ "$DRY_RUN" == 1 ]]; then
    curl -s -X POST "$KOKORO_URL/preprocess" \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg text "$TEXT" --arg mode "$MODE" '{text: $text} + (if $mode == "" then {} else {mode: $mode} end)')" \
        --max-time 10 | jq -r '"would_speak: \(.would_speak)  tone: \(.tone // "none")\n\(.text)"'
    exit 0
fi

# Stop any existing TTS playback
pkill -f "ffplay.*claude-tts" 2>/dev/null

echo "Speaking..."

SPEED="${KOKORO_SPEED:-1.0}"
VOLUME="${KOKORO_VOLUME:-100}"

curl -s -X POST "$KOKORO_URL/speak" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg text "$TEXT" --argjson speed "$SPEED" '{text: $text, speed: $speed}')" \
    --max-time 120 \
    2>/dev/null | ffplay -nodisp -autoexit -loglevel quiet -volume "$VOLUME" -f wav -window_title claude-tts -i pipe:0 2>/dev/null

echo "Done."
