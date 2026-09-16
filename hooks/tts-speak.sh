#!/bin/bash
# Claude Code TTS — Stop hook for auto-speak mode.
# Classification, summarizing, and preprocessing are handled server-side.
# This hook checks the voice state, asks the server whether the response is
# worth speaking, plays a chime for attention-worthy tones, and streams the
# audio so playback starts after the first sentence is synthesized.
#
# Voice state lives in a file written by voice.sh (on|off), not an env var:
# hooks are children of the Claude process, so a shell `export` never reaches
# them. Values:
#   off  — silent (default). On-demand "read that to me" still works.
#   auto — speak questions, completions, errors. Silent during code.
#
# Optional settings file, KEY=VALUE per line, read on every run so a change
# applies without restarting Claude: ~/.config/claude-code-tts/env
#   KOKORO_SPEED=1.15                        # 0.5 to 2.0
#   KOKORO_VOLUME=80                         # 0 to 100
#   TTS_CHIME_TONES="question error warning" # tones that get a chime; "" for none
#
# A new response interrupts whatever is still playing: newest wins.

CONFIG_FILE="${CLAUDE_TTS_CONFIG_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/claude-code-tts/env}"
[[ -f "$CONFIG_FILE" ]] && source "$CONFIG_FILE"

STATE_FILE="${CLAUDE_TTS_STATE_FILE:-$HOME/.local/state/claude-tts/state}"
if [[ -f "$STATE_FILE" ]]; then CLAUDE_TTS=$(cat "$STATE_FILE"); else CLAUDE_TTS="${CLAUDE_TTS:-off}"; fi
[[ "$CLAUDE_TTS" == "off" || "$CLAUDE_TTS" == "0" ]] && exit 0

KOKORO_URL="http://127.0.0.1:${KOKORO_PORT:-7723}"
CHIME_SCRIPT="${HOME}/.claude/scripts/tts-chime.sh"
SPEED="${KOKORO_SPEED:-1.0}"
VOLUME="${KOKORO_VOLUME:-100}"
CHIME_TONES="${TTS_CHIME_TONES-question error warning}"

HOOK_JSON=$(cat)
MESSAGE=$(echo "$HOOK_JSON" | jq -r '.last_assistant_message // empty' 2>/dev/null)
[[ -z "$MESSAGE" ]] && exit 0

# Daemon down: silent exit, never block Claude.
curl -s --max-time 1 "$KOKORO_URL/health" >/dev/null 2>&1 || exit 0

# Ask the server what it would do with this response. No synthesis happens
# here, so unspeakable responses cost nothing and the chime can play before
# the audio starts.
DECISION=$(curl -s -X POST "$KOKORO_URL/preprocess" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg text "$MESSAGE" '{text: $text, mode: "summary"}')" \
    --max-time 5 2>/dev/null)
[[ "$(echo "$DECISION" | jq -r '.would_speak' 2>/dev/null)" == "true" ]] || exit 0
TONE=$(echo "$DECISION" | jq -r '.tone // empty' 2>/dev/null)

# Interrupt whatever is still playing; this response is newer.
pkill -f "ffplay.*claude-tts" 2>/dev/null

(
    if [[ -n "$TONE" && " $CHIME_TONES " == *" $TONE "* && -x "$CHIME_SCRIPT" ]]; then
        bash "$CHIME_SCRIPT" "$TONE"
        sleep 0.3  # brief pause between chime and speech
    fi

    # Streamed: the server writes audio sentence by sentence and ffplay starts
    # as soon as the first one arrives. Killing ffplay closes the pipe, which
    # tells the server to stop synthesizing.
    curl -s -N -X POST "$KOKORO_URL/speak" \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg text "$MESSAGE" --argjson speed "$SPEED" '{text: $text, mode: "summary", speed: $speed}')" \
        --max-time 60 \
        2>/dev/null | ffplay -nodisp -autoexit -loglevel quiet -volume "$VOLUME" -f wav -window_title claude-tts -i pipe:0 2>/dev/null
) &

exit 0
