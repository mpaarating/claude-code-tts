#!/bin/bash
# Claude Code TTS — Stop hook for auto-speak mode.
# Text preprocessing (markdown stripping, pronunciation, truncation)
# is handled server-side. This hook just classifies and dispatches.
#
# Modes (set CLAUDE_TTS env var):
#   off  — silent (default). On-demand "read that to me" still works.
#   auto — speak questions, completions, errors. Silent during code.

MIN_MESSAGE_LEN=20
CODE_RATIO_THRESHOLD=40
LOCK_FILE="/tmp/claude-tts.lock"

CLAUDE_TTS="${CLAUDE_TTS:-off}"
[[ "$CLAUDE_TTS" == "off" || "$CLAUDE_TTS" == "0" ]] && exit 0

KOKORO_URL="http://127.0.0.1:${KOKORO_PORT:-7723}"

HOOK_JSON=$(cat)
MESSAGE=$(echo "$HOOK_JSON" | jq -r '.last_assistant_message // empty' 2>/dev/null)

[[ -z "$MESSAGE" ]] && exit 0
[[ ${#MESSAGE} -lt "$MIN_MESSAGE_LEN" ]] && exit 0

# Debounce: skip if another TTS is already playing
if [[ -f "$LOCK_FILE" ]]; then
    LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null)
    if kill -0 "$LOCK_PID" 2>/dev/null; then
        exit 0
    fi
    rm -f "$LOCK_FILE"
fi

# --- Classification: skip code-heavy responses ---
# Responses that are mostly code aren't useful to hear — variable names
# and syntax produce garbled speech. Better to stay silent.

TOTAL_LINES=$(echo "$MESSAGE" | wc -l | tr -d ' ')
CODE_LINES=$(echo "$MESSAGE" | awk '/^```/{inside=!inside; next} inside{count++} END{print count+0}')
if [[ "$TOTAL_LINES" -gt 0 ]]; then
    CODE_RATIO=$(( CODE_LINES * 100 / TOTAL_LINES ))
else
    CODE_RATIO=0
fi

[[ "$CODE_RATIO" -gt "$CODE_RATIO_THRESHOLD" ]] && exit 0

# --- Health check (silent exit for hooks) ---

curl -s --max-time 1 "$KOKORO_URL/health" >/dev/null 2>&1 || exit 0

# --- Speak (async, don't block Claude) ---

# Stop any existing TTS playback before starting new audio
pkill -f "ffplay.*claude-tts" 2>/dev/null

(
    echo $$ > "$LOCK_FILE"
    curl -s -X POST "$KOKORO_URL/speak" \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg text "$MESSAGE" '{text: $text, mode: "summary"}')" \
        --max-time 30 \
        2>/dev/null | ffplay -nodisp -autoexit -loglevel quiet -f wav -window_title claude-tts -i pipe:0 2>/dev/null
    rm -f "$LOCK_FILE"
) &

exit 0
