#!/bin/bash
# Karaoke mode — speak text with word-by-word terminal highlighting.
#
# Usage: tts-karaoke.sh "text to speak"
#    or: echo "text" | tts-karaoke.sh
#
# Shows the currently spoken word highlighted in the terminal,
# advancing in sync with audio playback.

KOKORO_URL="http://127.0.0.1:${KOKORO_PORT:-7723}"
AUDIO_FILE="/tmp/claude-tts-karaoke.wav"

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

# Generate audio and save to file (need duration info)
HTTP_CODE=$(curl -s -o "$AUDIO_FILE" -w '%{http_code}' -X POST "$KOKORO_URL/speak" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg text "$TEXT" '{text: $text}')" \
    --max-time 30 2>/dev/null)

[[ "$HTTP_CODE" != "200" || ! -s "$AUDIO_FILE" ]] && { echo "TTS generation failed"; exit 1; }

# Get audio duration in seconds using ffprobe
DURATION=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$AUDIO_FILE" 2>/dev/null)
[[ -z "$DURATION" ]] && { echo "Could not determine audio duration"; exit 1; }

# Preprocess text for display (strip markdown simply)
DISPLAY_TEXT=$(echo "$TEXT" | sed 's/```[^`]*```//g; s/`[^`]*`//g; s/\*\*\([^*]*\)\*\*/\1/g; s/\*\([^*]*\)\*/\1/g; s/^#* //; s/^[-*] //')

# Split into words
IFS=' ' read -ra WORDS <<< "$DISPLAY_TEXT"
WORD_COUNT=${#WORDS[@]}

[[ "$WORD_COUNT" -eq 0 ]] && exit 0

# Calculate time per word (seconds, as float via awk)
TIME_PER_WORD=$(awk "BEGIN {printf \"%.4f\", $DURATION / $WORD_COUNT}")

# ANSI escape codes
BOLD='\033[1m'
DIM='\033[2m'
UNDERLINE='\033[4m'
HIGHLIGHT='\033[1;36m'  # bold cyan
RESET='\033[0m'

# Start audio playback in background
ffplay -nodisp -autoexit -loglevel quiet -window_title claude-tts "$AUDIO_FILE" 2>/dev/null &
FFPLAY_PID=$!

# Hide cursor
printf '\033[?25l'

# Cleanup on exit
cleanup() {
    printf '\033[?25h'  # show cursor
    echo ""
    rm -f "$AUDIO_FILE"
}
trap cleanup EXIT

# Display words with highlighting
START_TIME=$(date +%s.%N 2>/dev/null || python3 -c "import time; print(f'{time.time():.6f}')")

for i in "${!WORDS[@]}"; do
    # Check if ffplay is still running
    if ! kill -0 "$FFPLAY_PID" 2>/dev/null; then
        break
    fi

    # Clear line and render: dim past words, highlight current, dim future
    printf '\r\033[K'

    # Show a window of words around the current one (±8 words)
    WINDOW_START=$((i - 8))
    WINDOW_END=$((i + 8))
    [[ $WINDOW_START -lt 0 ]] && WINDOW_START=0
    [[ $WINDOW_END -ge $WORD_COUNT ]] && WINDOW_END=$((WORD_COUNT - 1))

    for j in $(seq "$WINDOW_START" "$WINDOW_END"); do
        if [[ $j -lt $i ]]; then
            printf "${DIM}%s${RESET} " "${WORDS[$j]}"
        elif [[ $j -eq $i ]]; then
            printf "${HIGHLIGHT}%s${RESET} " "${WORDS[$j]}"
        else
            printf "%s " "${WORDS[$j]}"
        fi
    done

    # Progress indicator
    PROGRESS=$(( (i + 1) * 100 / WORD_COUNT ))
    printf "  ${DIM}[%d%%]${RESET}" "$PROGRESS"

    # Wait for next word timing
    # Use python for sub-second sleep since bash sleep only does integers on some systems
    python3 -c "import time; time.sleep($TIME_PER_WORD)" 2>/dev/null || sleep 1
done

# Wait for audio to finish
wait "$FFPLAY_PID" 2>/dev/null

printf '\r\033[K'
echo "Done."
