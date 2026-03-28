#!/bin/bash
set -euo pipefail

# Claude Code TTS — Uninstaller
# Supports macOS (launchd) and Linux (systemd).

INSTALL_DIR="$HOME/.local/share/claude-code-tts"
SERVICE_NAME="kokoro-tts"
PLATFORM="$(uname -s)"

echo "=== Claude Code TTS Uninstaller ==="
echo ""

# Stop and remove daemon (platform-specific)
if [[ "$PLATFORM" == "Darwin" ]]; then
    PLIST_NAME="com.$(whoami).${SERVICE_NAME}"
    PLIST_FILE="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

    if launchctl list 2>/dev/null | grep -q "$PLIST_NAME"; then
        echo "Stopping daemon..."
        launchctl unload "$PLIST_FILE" 2>/dev/null || true
    fi

    if [[ -f "$PLIST_FILE" ]]; then
        rm "$PLIST_FILE"
        echo "  Removed LaunchAgent."
    fi

elif [[ "$PLATFORM" == "Linux" ]]; then
    SERVICE_FILE="$HOME/.config/systemd/user/${SERVICE_NAME}.service"

    if systemctl --user is-active "$SERVICE_NAME" &>/dev/null; then
        echo "Stopping daemon..."
        systemctl --user stop "$SERVICE_NAME" 2>/dev/null || true
        systemctl --user disable "$SERVICE_NAME" 2>/dev/null || true
    fi

    if [[ -f "$SERVICE_FILE" ]]; then
        rm "$SERVICE_FILE"
        systemctl --user daemon-reload 2>/dev/null || true
        echo "  Removed systemd service."
    fi
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
         "$HOME/.claude/hooks/tts-workflow.sh" \
         "$HOME/.claude/scripts/tts-speak.sh" \
         "$HOME/.claude/scripts/tts-stop.sh" \
         "$HOME/.claude/scripts/tts-chime.sh" \
         "$HOME/.claude/scripts/tts-log.sh"; do
    if [[ -f "$f" ]]; then
        rm "$f"
        echo "  Removed $f"
    fi
done

echo ""
echo "Done. Remember to remove the TTS hooks from ~/.claude/settings.json"
echo "and the Voice Output section from ~/.claude/CLAUDE.md manually."
