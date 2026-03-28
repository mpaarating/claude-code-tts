#!/bin/bash
# Claude Code TTS — Stop hook for auto-speak mode.
# Classification and preprocessing are handled server-side.
# This hook just dispatches the raw message.
#
# Modes (set CLAUDE_TTS env var):
#   off  — silent (default). On-demand "read that to me" still works.
#   auto — speak questions, completions, errors. Silent during code.

LOCK_FILE="/tmp/claude-tts.lock"

CLAUDE_TTS="${CLAUDE_TTS:-off}"
[[ "$CLAUDE_TTS" == "off" || "$CLAUDE_TTS" == "0" ]] && exit 0

KOKORO_URL="http://127.0.0.1:${KOKORO_PORT:-7723}"

HOOK_JSON=$(cat)
MESSAGE=$(echo "$HOOK_JSON" | jq -r '.last_assistant_message // empty' 2>/dev/null)

[[ -z "$MESSAGE" ]] && exit 0

# Debounce: skip if another TTS is already playing
if [[ -f "$LOCK_FILE" ]]; then
    LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null)
    if kill -0 "$LOCK_PID" 2>/dev/null; then
        exit 0
    fi
    rm -f "$LOCK_FILE"
fi

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
