#!/bin/bash
set -euo pipefail

# Claude Code TTS — Uninstaller

INSTALL_DIR="$HOME/.local/share/claude-code-tts"
PLIST_NAME="com.$(whoami).kokoro-tts"
PLIST_FILE="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "=== Claude Code TTS Uninstaller ==="
echo ""

# Stop daemon
if launchctl list | grep -q "$PLIST_NAME"; then
    echo "Stopping daemon..."
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
fi

# Remove plist
if [[ -f "$PLIST_FILE" ]]; then
    rm "$PLIST_FILE"
    echo "  Removed LaunchAgent."
fi

# Remove install directory (venv, server, models)
if [[ -d "$INSTALL_DIR" ]]; then
    read -p "Remove $INSTALL_DIR including models (~340MB)? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$INSTALL_DIR"
        echo "  Removed install directory."
    else
        echo "  Kept install directory."
    fi
fi

# Remove hooks + scripts
for f in "$HOME/.claude/hooks/tts-speak.sh" \
         "$HOME/.claude/hooks/tts-plan-reader.sh" \
         "$HOME/.claude/scripts/tts-speak.sh"; do
    if [[ -f "$f" ]]; then
        rm "$f"
        echo "  Removed $f"
    fi
done

echo ""
echo "Done. Remember to remove the TTS hooks from ~/.claude/settings.json"
echo "and the Voice Output section from ~/.claude/CLAUDE.md manually."
