#!/bin/bash
# Play a notification chime based on event tone.
# Usage: tts-chime.sh <tone>
#   tone: error | completion | question | warning
#
# macOS: uses built-in system sounds (zero deps)
# Linux: uses paplay with bundled WAV files

TONE="${1:-}"
[[ -z "$TONE" ]] && exit 0

PLATFORM="$(uname -s)"

if [[ "$PLATFORM" == "Darwin" ]]; then
    case "$TONE" in
        error)      afplay /System/Library/Sounds/Basso.aiff &;;
        completion) afplay /System/Library/Sounds/Glass.aiff &;;
        question)   afplay /System/Library/Sounds/Purr.aiff &;;
        warning)    afplay /System/Library/Sounds/Submarine.aiff &;;
    esac
elif [[ "$PLATFORM" == "Linux" ]]; then
    SOUNDS_DIR="${HOME}/.local/share/claude-code-tts/sounds"
    case "$TONE" in
        error)      paplay "$SOUNDS_DIR/error.wav" &;;
        completion) paplay "$SOUNDS_DIR/completion.wav" &;;
        question)   paplay "$SOUNDS_DIR/question.wav" &;;
        warning)    paplay "$SOUNDS_DIR/warning.wav" &;;
    esac
fi
