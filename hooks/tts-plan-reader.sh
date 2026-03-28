#!/bin/bash
# Auto-read plan files aloud when ExitPlanMode is called.
# Fires as a PostToolUse hook so you hear the plan while
# looking at the approve/reject prompt.

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

# Extract a spoken summary — first ~60 lines / 2000 chars
CLEAN=$(awk '/^```/{skip=!skip; next} !skip{print}' "$PLAN_FILE" | sed -E \
    -e 's/\*\*([^*]+)\*\*/\1/g' \
    -e 's/\*([^*]+)\*/\1/g' \
    -e 's/`([^`]+)`/\1/g' \
    -e 's/^#+ //' \
    -e 's/^- //' \
    -e 's/^\* //' \
    -e 's/^[0-9]+\. //' \
    -e 's/\[([^]]+)\]\([^)]+\)/\1/g' \
    -e '/^[[:space:]]*$/d' \
    -e '/^\|/d' | head -60 | tr '\n' ' ' | sed 's/  */ /g' | cut -c1-2000)

[[ -z "$CLEAN" ]] && exit 0

(
    curl -s -X POST "$KOKORO_URL/speak-long" \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg text "$CLEAN" '{text: $text}')" \
        --max-time 120 \
        2>/dev/null | ffplay -nodisp -autoexit -loglevel quiet -i pipe:0 2>/dev/null
) &

exit 0
