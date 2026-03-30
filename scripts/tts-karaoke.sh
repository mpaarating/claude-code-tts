#!/bin/bash
# Karaoke mode — display text for reading while audio plays in background.
#
# Usage: tts-karaoke.sh "text to speak"
#    or: echo "text" | tts-karaoke.sh
#
# Prints the text so the user can read along while hearing it spoken.
# In a real terminal, adds word-by-word ANSI highlighting (--animate flag).

KOKORO_URL="http://127.0.0.1:${KOKORO_PORT:-7723}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DISPLAY_SCRIPT="$SCRIPT_DIR/karaoke_display.py"
HEADER_FILE="/tmp/claude-tts-karaoke-headers.txt"
AUDIO_FILE="/tmp/claude-tts-karaoke.wav"

# Parse flags
ANIMATE=false
if [[ "$1" == "--animate" ]]; then
    ANIMATE=true
    shift
fi

# Get text from argument or stdin
if [[ -n "$1" ]]; then
    TEXT="$1"
else
    TEXT=$(cat)
fi

[[ -z "$TEXT" ]] && { echo "No text provided"; exit 1; }

# Check daemon
if ! curl -s --max-time 2 "$KOKORO_URL/health" >/dev/null 2>&1; then
    echo "Kokoro daemon not running."
    exit 1
fi

# Stop existing playback
pkill -f "ffplay.*claude-tts" 2>/dev/null

# Cleanup on exit
FFPLAY_PID=""
cleanup() {
    [[ -n "$FFPLAY_PID" ]] && kill "$FFPLAY_PID" 2>/dev/null
    rm -f "$HEADER_FILE" "$AUDIO_FILE"
}
trap cleanup EXIT

# Generate audio — save WAV + response headers
HTTP_CODE=$(curl -s -o "$AUDIO_FILE" -D "$HEADER_FILE" -w '%{http_code}' \
    -X POST "$KOKORO_URL/speak" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg text "$TEXT" '{text: $text}')" \
    --max-time 30 2>/dev/null)

[[ "$HTTP_CODE" != "200" || ! -s "$AUDIO_FILE" ]] && { echo "TTS generation failed"; exit 1; }

DURATION=$(grep -i "X-TTS-Duration:" "$HEADER_FILE" | tr -d '\r' | awk '{print $2}')

# Play audio in background
ffplay -nodisp -autoexit -loglevel quiet -window_title claude-tts "$AUDIO_FILE" 2>/dev/null &
FFPLAY_PID=$!

# Strip markdown for display
DISPLAY_TEXT=$(echo "$TEXT" | sed '
    s/```[^`]*```//g
    s/`[^`]*`//g
    s/\*\*\([^*]*\)\*\*/\1/g
    s/\*\([^*]*\)\*/\1/g
    s/^#* //
    s/^[-*] //
')

# Display text — animated ANSI in terminal, plain text otherwise
if [[ "$ANIMATE" == "true" ]] && [[ -n "$DURATION" ]] && [[ -e /dev/tty ]] && python3 -c "open('/dev/tty','w')" 2>/dev/null; then
    echo "$DISPLAY_TEXT" | python3 "$DISPLAY_SCRIPT" --duration "$DURATION"
else
    echo ""
    echo "$DISPLAY_TEXT"
    echo ""
fi

# Wait for audio to finish
wait "$FFPLAY_PID" 2>/dev/null
FFPLAY_PID=""
