#!/bin/bash
# Voice session control — single source of truth for auto-speak.
# The Stop hook (tts-speak.sh) and plan-reader hook read this state file.
# Env vars can't work: hooks are children of the Claude process, not our shell.
#
# Usage: voice.sh on|off|toggle|status
STATE_FILE="${CLAUDE_TTS_STATE_FILE:-$HOME/.local/state/claude-tts/state}"
mkdir -p "$(dirname "$STATE_FILE")"
_read() { [[ -f "$STATE_FILE" ]] && cat "$STATE_FILE" || echo off; }
case "${1:-status}" in
  on|auto)   echo auto > "$STATE_FILE"; echo "🔊 voice ON (auto-speak)";;
  off|mute)  echo off  > "$STATE_FILE"; pkill -f "ffplay.*claude-tts" 2>/dev/null; echo "🔇 voice OFF";;
  toggle)    if [[ "$(_read)" == auto ]]; then echo off > "$STATE_FILE"; pkill -f "ffplay.*claude-tts" 2>/dev/null; echo "🔇 voice OFF"; else echo auto > "$STATE_FILE"; echo "🔊 voice ON (auto-speak)"; fi;;
  status)    [[ "$(_read)" == auto ]] && echo "🔊 voice ON" || echo "🔇 voice OFF";;
  *) echo "usage: voice.sh on|off|toggle|status"; exit 1;;
esac
