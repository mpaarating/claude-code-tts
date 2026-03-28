#!/bin/bash
# Claude Code TTS — Stop hook for auto-speak mode.
# Speaks conversational responses, stays silent during code output.
#
# Modes (set CLAUDE_TTS env var):
#   off  — silent (default). On-demand "read that to me" still works.
#   auto — speak questions, completions, errors. Silent during code.

CLAUDE_TTS="${CLAUDE_TTS:-off}"
[[ "$CLAUDE_TTS" == "off" || "$CLAUDE_TTS" == "0" ]] && exit 0

KOKORO_URL="http://127.0.0.1:${KOKORO_PORT:-7723}/speak"
LOCK_FILE="/tmp/claude-tts.lock"

INPUT=$(cat)
MESSAGE=$(echo "$INPUT" | jq -r '.last_assistant_message // empty' 2>/dev/null)

[[ -z "$MESSAGE" ]] && exit 0
[[ ${#MESSAGE} -lt 20 ]] && exit 0

# Debounce: skip if another TTS is already playing
if [[ -f "$LOCK_FILE" ]]; then
    LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null)
    if kill -0 "$LOCK_PID" 2>/dev/null; then
        exit 0
    fi
    rm -f "$LOCK_FILE"
fi

# --- Classification ---

TOTAL_LINES=$(echo "$MESSAGE" | wc -l | tr -d ' ')
CODE_LINES=$(echo "$MESSAGE" | awk '/^```/{inside=!inside; next} inside{count++} END{print count+0}')
if [[ "$TOTAL_LINES" -gt 0 ]]; then
    CODE_RATIO=$(( CODE_LINES * 100 / TOTAL_LINES ))
else
    CODE_RATIO=0
fi

# Silent if >40% code
[[ "$CODE_RATIO" -gt 40 ]] && exit 0

# --- Extract speakable text ---

strip_markdown() {
    awk '/^```/{skip=!skip; next} !skip{print}' | sed -E \
        -e 's/\*\*([^*]+)\*\*/\1/g' \
        -e 's/\*([^*]+)\*/\1/g' \
        -e 's/`([^`]+)`/\1/g' \
        -e 's/^#+ //' \
        -e 's/^- //' \
        -e 's/^\* //' \
        -e 's/^[0-9]+\. //' \
        -e 's/\[([^]]+)\]\([^)]+\)/\1/g' \
        -e '/^[[:space:]]*$/d' \
        -e '/^\|/d'
}

CLEAN=$(echo "$MESSAGE" | strip_markdown)
[[ -z "$CLEAN" ]] && exit 0

CHAR_COUNT=${#CLEAN}
if [[ "$CHAR_COUNT" -le 200 ]]; then
    SPEAK_TEXT="$CLEAN"
else
    SPEAK_TEXT=$(echo "$CLEAN" | tr '\n' ' ' | sed -E 's/([.!?])[[:space:]]+/\1\n/g' | head -3 | tr '\n' ' ' | sed 's/[[:space:]]*$//')
    if [[ ${#SPEAK_TEXT} -lt 20 ]]; then
        SPEAK_TEXT="${CLEAN:0:300}"
    fi
fi

SPEAK_TEXT="${SPEAK_TEXT:0:800}"

# --- Speak (async, don't block Claude) ---

(
    echo $$ > "$LOCK_FILE"
    curl -s -X POST "$KOKORO_URL" \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg text "$SPEAK_TEXT" '{text: $text}')" \
        --max-time 30 \
        2>/dev/null | ffplay -nodisp -autoexit -loglevel quiet -i pipe:0 2>/dev/null
    rm -f "$LOCK_FILE"
) &

exit 0
