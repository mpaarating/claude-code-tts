#!/bin/bash
# Stop any currently playing TTS audio.
# Can be called manually, via hotkey, or by Claude ("stop", "mute").
#
# Usage: tts-stop.sh

if pkill -f "ffplay.*claude-tts" 2>/dev/null; then
    echo "Stopped."
else
    echo "Nothing playing."
fi

# Clean up stale lock file
rm -f /tmp/claude-tts.lock
