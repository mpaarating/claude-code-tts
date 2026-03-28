#!/bin/bash
# Auto-read plan files aloud when ExitPlanMode is called.
# Text preprocessing (markdown stripping, pronunciation, truncation)
# is handled server-side. This hook just reads and dispatches.
#
# Fires as a PostToolUse hook so you hear the plan while
# looking at the approve/reject prompt.

MAX_PLAN_LINES=60
MAX_PLAN_CHARS=2000

KOKORO_URL="http://127.0.0.1:${KOKORO_PORT:-7723}"

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)

[[ "$TOOL_NAME" != "ExitPlanMode" ]] && exit 0

# Check daemon is running
curl -s --max-time 1 "$KOKORO_URL/health" >/dev/null 2>&1 || exit 0

# Find the most recently modified plan file
PLAN_DIR="$HOME/.config/claude/plans"
[[ ! -d "$PLAN_DIR" ]] && exit 0

PLAN_FILE=$(ls -t "$PLAN_DIR"/*.md 2>/dev/null | head -1)
[[ -z "$PLAN_FILE" || ! -f "$PLAN_FILE" ]] && exit 0

# Read plan, truncate to limits — server handles markdown cleanup
TEXT=$(head -"$MAX_PLAN_LINES" "$PLAN_FILE" | cut -c1-"$MAX_PLAN_CHARS")
[[ -z "$TEXT" ]] && exit 0

# Stop any existing TTS playback
pkill -f "ffplay.*claude-tts" 2>/dev/null

(
    curl -s -X POST "$KOKORO_URL/speak" \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg text "$TEXT" '{text: $text}')" \
        --max-time 120 \
        2>/dev/null | ffplay -nodisp -autoexit -loglevel quiet -f wav -window_title claude-tts -i pipe:0 2>/dev/null
) &

exit 0
