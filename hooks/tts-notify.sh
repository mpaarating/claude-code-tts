#!/bin/bash
# Claude Code TTS — Notification hook. Speaks a one-line nudge when Claude is
# blocked on you and you may not be looking: a permission prompt by default,
# an idle session if you opt in. Silent unless voice is on (voice.sh on).
#
# Settings (in ~/.config/claude-code-tts/env, read on every run):
#   TTS_NOTIFY_TYPES="permission_prompt"              # default
#   TTS_NOTIFY_TYPES="permission_prompt idle_prompt"  # also nudge when idle
#
# Claude Code sends `notification_type` (permission_prompt, idle_prompt,
# auth_success, elicitation_dialog) and a human `message`. Older builds send
# only the message, so the type is inferred from it when missing.

CONFIG_FILE="${CLAUDE_TTS_CONFIG_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/claude-code-tts/env}"
[[ -f "$CONFIG_FILE" ]] && source "$CONFIG_FILE"

STATE_FILE="${CLAUDE_TTS_STATE_FILE:-$HOME/.local/state/claude-tts/state}"
if [[ -f "$STATE_FILE" ]]; then CLAUDE_TTS=$(cat "$STATE_FILE"); else CLAUDE_TTS="${CLAUDE_TTS:-off}"; fi
[[ "$CLAUDE_TTS" == "off" || "$CLAUDE_TTS" == "0" ]] && exit 0

KOKORO_URL="http://127.0.0.1:${KOKORO_PORT:-7723}"
CHIME_SCRIPT="${HOME}/.claude/scripts/tts-chime.sh"
SPEED="${KOKORO_SPEED:-1.0}"
VOLUME="${KOKORO_VOLUME:-100}"
NOTIFY_TYPES="${TTS_NOTIFY_TYPES-permission_prompt}"

HOOK_JSON=$(cat)
TYPE=$(echo "$HOOK_JSON" | jq -r '.notification_type // empty' 2>/dev/null)
MESSAGE=$(echo "$HOOK_JSON" | jq -r '.message // empty' 2>/dev/null)
CWD=$(echo "$HOOK_JSON" | jq -r '.cwd // empty' 2>/dev/null)

if [[ -z "$TYPE" ]]; then
    case "$MESSAGE" in
        *permission*) TYPE="permission_prompt" ;;
        *waiting*)    TYPE="idle_prompt" ;;
        *)            exit 0 ;;
    esac
fi
[[ " $NOTIFY_TYPES " == *" $TYPE "* ]] || exit 0

# Name the session by its project so parallel sessions are distinguishable.
PROJECT=$(basename "${CLAUDE_PROJECT_DIR:-$CWD}" 2>/dev/null)
PROJECT="${PROJECT//[-_]/ }"

case "$TYPE" in
    permission_prompt)
        # The message already reads like "Claude needs your permission to use Bash".
        TEXT="${PROJECT:+$PROJECT: }${MESSAGE:-Claude needs your permission}"
        TONE="warning"
        ;;
    idle_prompt)
        TEXT="${PROJECT:+$PROJECT }is waiting on you."
        TONE="question"
        ;;
    *)
        exit 0
        ;;
esac

curl -s --max-time 1 "$KOKORO_URL/health" >/dev/null 2>&1 || exit 0

# Newest wins: a prompt that needs an answer beats whatever is still playing.
pkill -f "ffplay.*claude-tts" 2>/dev/null

(
    if [[ -x "$CHIME_SCRIPT" ]]; then
        bash "$CHIME_SCRIPT" "$TONE"
        sleep 0.3
    fi
    curl -s -N -X POST "$KOKORO_URL/speak" \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg text "$TEXT" --arg voice "" --argjson speed "$SPEED" '{text: $text, speed: $speed}')" \
        --max-time 30 \
        2>/dev/null | ffplay -nodisp -autoexit -loglevel quiet -volume "$VOLUME" -f wav -window_title claude-tts -i pipe:0 2>/dev/null
) &

exit 0
