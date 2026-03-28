#!/bin/bash
# Claude Code TTS — Stop hook for auto-speak mode.
# Classification and preprocessing are handled server-side.
# This hook dispatches the raw message and plays notification chimes.
#
# Modes (set CLAUDE_TTS env var):
#   off  — silent (default). On-demand "read that to me" still works.
#   auto — speak questions, completions, errors. Silent during code.

LOCK_FILE="/tmp/claude-tts.lock"
CHIME_SCRIPT="${HOME}/.claude/scripts/tts-chime.sh"

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

    # Use -D- to capture response headers (tone) alongside body
    RESPONSE=$(curl -s -D- -X POST "$KOKORO_URL/speak" \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg text "$MESSAGE" '{text: $text, mode: "summary"}')" \
        --max-time 30 \
        -o /tmp/claude-tts-audio.wav \
        2>/dev/null)

    TONE=$(echo "$RESPONSE" | grep -i "X-TTS-Tone:" | tr -d '\r' | awk '{print $2}')
    HTTP_CODE=$(echo "$RESPONSE" | head -1 | awk '{print $2}')

    # Play chime if tone detected
    if [[ -n "$TONE" && -x "$CHIME_SCRIPT" ]]; then
        bash "$CHIME_SCRIPT" "$TONE"
        sleep 0.3  # brief pause between chime and speech
    fi

    # Play speech if server returned audio (200), skip if 204 (trivial)
    if [[ "$HTTP_CODE" == "200" && -s /tmp/claude-tts-audio.wav ]]; then
        ffplay -nodisp -autoexit -loglevel quiet -f wav -window_title claude-tts /tmp/claude-tts-audio.wav 2>/dev/null
    fi

    rm -f "$LOCK_FILE" /tmp/claude-tts-audio.wav
) &

exit 0
