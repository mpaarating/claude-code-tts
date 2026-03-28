#!/bin/bash
# On-demand TTS — called by Claude when user says "read that to me"
# Usage: tts-speak.sh "text to speak"
#    or: echo "text" | tts-speak.sh
#    or: tts-speak.sh --file /path/to/file

KOKORO_URL="http://127.0.0.1:${KOKORO_PORT:-7723}"

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

# Strip markdown
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

CLEAN=$(echo "$TEXT" | strip_markdown | tr '\n' ' ' | sed 's/  */ /g')
[[ -z "$CLEAN" ]] && { echo "Nothing speakable after stripping markdown"; exit 0; }

echo "Speaking..."

if [[ ${#CLEAN} -le 500 ]]; then
    ENDPOINT="/speak"
else
    ENDPOINT="/speak-long"
fi

curl -s -X POST "${KOKORO_URL}${ENDPOINT}" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg text "$CLEAN" '{text: $text}')" \
    --max-time 120 \
    2>/dev/null | ffplay -nodisp -autoexit -loglevel quiet -i pipe:0 2>/dev/null

echo "Done."
