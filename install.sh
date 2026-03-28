#!/bin/bash
set -euo pipefail

# Claude Code TTS — Installer
# Local, free text-to-speech for Claude Code using Kokoro TTS.
# Supports macOS (launchd) and Linux (systemd).

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$HOME/.local/share/claude-code-tts"
MODELS_DIR="$INSTALL_DIR/models"
HOOKS_DIR="$HOME/.claude/hooks"
SCRIPTS_DIR="$HOME/.claude/scripts"
PORT="${KOKORO_PORT:-7723}"
VOICE="${KOKORO_VOICE:-af_heart}"
PLATFORM="$(uname -s)"
MAX_WAIT_SECS=20
WITH_HOTKEYS=false

for arg in "$@"; do
    case "$arg" in
        --with-hotkeys) WITH_HOTKEYS=true ;;
    esac
done

echo "=== Claude Code TTS Installer ==="
echo "Platform: $PLATFORM"
echo ""

# --- Check dependencies ---

echo "Checking dependencies..."

if ! command -v jq &>/dev/null; then
    if [[ "$PLATFORM" == "Darwin" ]]; then
        echo "ERROR: jq is required. Install with: brew install jq"
    else
        echo "ERROR: jq is required. Install with: sudo apt install jq (or your package manager)"
    fi
    exit 1
fi

if ! command -v ffplay &>/dev/null; then
    if [[ "$PLATFORM" == "Darwin" ]]; then
        echo "ERROR: ffplay is required. Install with: brew install ffmpeg"
    else
        echo "ERROR: ffplay is required. Install with: sudo apt install ffmpeg (or your package manager)"
    fi
    exit 1
fi

# Find a suitable Python (3.10+)
PYTHON=""
for py in python3.14 python3.13 python3.12 python3.11 python3.10; do
    if command -v "$py" &>/dev/null; then
        PYTHON="$py"
        break
    fi
done

# Check homebrew python (macOS)
if [[ -z "$PYTHON" && "$PLATFORM" == "Darwin" ]]; then
    for py in /opt/homebrew/bin/python3.{14,13,12,11,10}; do
        if [[ -x "$py" ]]; then
            PYTHON="$py"
            break
        fi
    done
fi

if [[ -z "$PYTHON" ]]; then
    if [[ "$PLATFORM" == "Darwin" ]]; then
        echo "ERROR: Python 3.10+ is required. Install with: brew install python@3.13"
    else
        echo "ERROR: Python 3.10+ is required. Install with: sudo apt install python3.12 python3.12-venv"
    fi
    exit 1
fi

PY_VERSION=$($PYTHON --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
echo "  Python: $PYTHON ($PY_VERSION)"
echo "  jq: $(which jq)"
echo "  ffplay: $(which ffplay)"
echo ""

# --- Create venv + install packages ---

echo "Setting up Python environment..."
mkdir -p "$INSTALL_DIR" "$MODELS_DIR"

if [[ ! -d "$INSTALL_DIR/venv" ]]; then
    $PYTHON -m venv "$INSTALL_DIR/venv"
fi

"$INSTALL_DIR/venv/bin/pip" install -q kokoro-onnx soundfile numpy 2>&1 | tail -1
echo "  Packages installed."

# --- Download models (if not present) ---

MODEL_FILE="$MODELS_DIR/kokoro-v1.0.onnx"
VOICES_FILE="$MODELS_DIR/voices-v1.0.bin"

if [[ ! -f "$MODEL_FILE" ]]; then
    echo "Downloading Kokoro model (~310MB)..."
    curl -L --progress-bar -o "$MODEL_FILE" \
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
else
    echo "  Model already downloaded."
fi

if [[ ! -f "$VOICES_FILE" ]]; then
    echo "Downloading voice data (~27MB)..."
    curl -L --progress-bar -o "$VOICES_FILE" \
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
else
    echo "  Voices already downloaded."
fi

# --- Copy server + config ---

cp "$REPO_DIR/server/kokoro-server.py" "$INSTALL_DIR/kokoro-server.py"
cp "$REPO_DIR/server/preprocess.py" "$INSTALL_DIR/preprocess.py"
cp "$REPO_DIR/server/mcp-server.py" "$INSTALL_DIR/mcp-server.py"
if [[ -f "$REPO_DIR/server/pronunciation.json" ]]; then
    # Only copy if user hasn't customized their own
    if [[ ! -f "$INSTALL_DIR/pronunciation.json" ]]; then
        cp "$REPO_DIR/server/pronunciation.json" "$INSTALL_DIR/pronunciation.json"
    fi
fi
echo "  Server installed."

# --- Copy hooks + scripts ---

mkdir -p "$HOOKS_DIR" "$SCRIPTS_DIR"

cp "$REPO_DIR/hooks/tts-speak.sh" "$HOOKS_DIR/tts-speak.sh"
cp "$REPO_DIR/hooks/tts-plan-reader.sh" "$HOOKS_DIR/tts-plan-reader.sh"
cp "$REPO_DIR/scripts/tts-speak.sh" "$SCRIPTS_DIR/tts-speak.sh"
cp "$REPO_DIR/scripts/tts-stop.sh" "$SCRIPTS_DIR/tts-stop.sh"
cp "$REPO_DIR/scripts/tts-chime.sh" "$SCRIPTS_DIR/tts-chime.sh"
chmod +x "$HOOKS_DIR/tts-speak.sh" "$HOOKS_DIR/tts-plan-reader.sh" "$SCRIPTS_DIR/tts-speak.sh" "$SCRIPTS_DIR/tts-stop.sh" "$SCRIPTS_DIR/tts-chime.sh"
echo "  Hooks and scripts installed."

# --- Create daemon (platform-specific) ---

SERVICE_NAME="kokoro-tts"

if [[ "$PLATFORM" == "Darwin" ]]; then
    # macOS: launchd plist
    PLIST_DIR="$HOME/Library/LaunchAgents"
    PLIST_NAME="com.$(whoami).${SERVICE_NAME}"
    mkdir -p "$PLIST_DIR"
    cat > "$PLIST_DIR/${PLIST_NAME}.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${INSTALL_DIR}/venv/bin/python3</string>
        <string>${INSTALL_DIR}/kokoro-server.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <!-- Lower CPU priority so TTS doesn't compete with dev tools -->
    <key>Nice</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>/tmp/kokoro-tts.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/kokoro-tts.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>KOKORO_PORT</key>
        <string>${PORT}</string>
        <key>KOKORO_VOICE</key>
        <string>${VOICE}</string>
    </dict>
</dict>
</plist>
EOF
    echo "  LaunchAgent created."

    # Start daemon
    echo ""
    echo "Starting Kokoro TTS daemon..."
    launchctl unload "$PLIST_DIR/${PLIST_NAME}.plist" 2>/dev/null || true
    sleep 1
    launchctl load "$PLIST_DIR/${PLIST_NAME}.plist"

elif [[ "$PLATFORM" == "Linux" ]]; then
    # Linux: systemd user service
    SYSTEMD_DIR="$HOME/.config/systemd/user"
    mkdir -p "$SYSTEMD_DIR"
    cat > "$SYSTEMD_DIR/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Kokoro TTS daemon for Claude Code
After=network.target

[Service]
Type=simple
ExecStart=${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/kokoro-server.py
Restart=always
RestartSec=5
Nice=10
Environment=KOKORO_PORT=${PORT}
Environment=KOKORO_VOICE=${VOICE}
StandardOutput=append:/tmp/kokoro-tts.log
StandardError=append:/tmp/kokoro-tts.log

[Install]
WantedBy=default.target
EOF
    echo "  systemd user service created."

    # Start daemon
    echo ""
    echo "Starting Kokoro TTS daemon..."
    systemctl --user daemon-reload
    systemctl --user enable "${SERVICE_NAME}.service"
    systemctl --user restart "${SERVICE_NAME}.service"

else
    echo "WARNING: Unsupported platform '$PLATFORM'. Start the daemon manually:"
    echo "  ${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/kokoro-server.py"
fi

# Wait for model to load
echo -n "  Waiting for model to load"
for i in $(seq 1 "$MAX_WAIT_SECS"); do
    if curl -s --max-time 1 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
        echo " ready!"
        break
    fi
    echo -n "."
    sleep 1
done

if ! curl -s --max-time 2 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    echo ""
    echo "WARNING: Daemon didn't start. Check /tmp/kokoro-tts.log"
    exit 1
fi

# --- Configure Claude Code ---

echo ""
echo "Configuring Claude Code hooks..."

SETTINGS_FILE="$HOME/.claude/settings.json"

if [[ -f "$SETTINGS_FILE" ]]; then
    if grep -q "tts-speak.sh" "$SETTINGS_FILE"; then
        echo "  Hooks already configured in settings.json."
    else
        echo ""
        echo "  Add these hooks to your ~/.claude/settings.json manually:"
        echo ""
        echo '  In the "Stop" array:'
        echo '    {'
        echo '      "hooks": [{'
        echo '        "type": "command",'
        echo "        \"command\": \"bash $HOOKS_DIR/tts-speak.sh\","
        echo '        "timeout": 15'
        echo '      }]'
        echo '    }'
        echo ""
        echo '  In the "PostToolUse" array:'
        echo '    {'
        echo '      "matcher": "ExitPlanMode",'
        echo '      "hooks": [{'
        echo '        "type": "command",'
        echo "        \"command\": \"bash $HOOKS_DIR/tts-plan-reader.sh\","
        echo '        "timeout": 5'
        echo '      }]'
        echo '    }'
    fi
else
    echo "  No settings.json found. Create one or add hooks manually."
fi

# --- Add CLAUDE.md instructions ---

CLAUDE_MD="$HOME/.claude/CLAUDE.md"
if [[ -f "$CLAUDE_MD" ]] && ! grep -q "Voice Output" "$CLAUDE_MD"; then
    echo ""
    echo "  Add this to your ~/.claude/CLAUDE.md:"
    echo ""
    cat <<'INSTRUCTIONS'
## Voice Output (Kokoro TTS)

**On-demand**: When the user says "read that to me", "say that", "speak", or similar:
```bash
bash ~/.claude/scripts/tts-speak.sh "text to speak"
```
The script handles markdown stripping, chunking, and seamless playback. Runs locally, free.

**Session voice toggle**: "voice on" / "voice off":
```bash
export CLAUDE_TTS=auto   # auto-speak conversational responses
export CLAUDE_TTS=off    # back to silent
```
INSTRUCTIONS
fi

# --- Hotkeys (optional) ---

if [[ "$WITH_HOTKEYS" == "true" ]]; then
    echo ""
    echo "Setting up global hotkeys..."
    if [[ "$PLATFORM" == "Darwin" ]]; then
        if command -v skhd &>/dev/null; then
            SKHD_DIR="$HOME/.config/skhd"
            mkdir -p "$SKHD_DIR"
            if [[ -f "$SKHD_DIR/skhdrc" ]] && grep -q "claude-tts" "$SKHD_DIR/skhdrc"; then
                echo "  skhd hotkeys already configured."
            else
                cat "$REPO_DIR/config/skhdrc" >> "$SKHD_DIR/skhdrc"
                echo "  skhd hotkeys added to $SKHD_DIR/skhdrc"
                skhd --restart-service 2>/dev/null || true
            fi
        else
            echo "  skhd not found. Install with: brew install skhd && skhd --start-service"
            echo "  Then re-run: bash install.sh --with-hotkeys"
        fi
    elif [[ "$PLATFORM" == "Linux" ]]; then
        if command -v sxhkd &>/dev/null; then
            SXHKD_DIR="$HOME/.config/sxhkd"
            mkdir -p "$SXHKD_DIR"
            if [[ -f "$SXHKD_DIR/sxhkdrc" ]] && grep -q "claude-tts" "$SXHKD_DIR/sxhkdrc"; then
                echo "  sxhkd hotkeys already configured."
            else
                cat "$REPO_DIR/config/sxhkdrc" >> "$SXHKD_DIR/sxhkdrc"
                echo "  sxhkd hotkeys added."
            fi
        else
            echo "  sxhkd not found. Install with: sudo apt install sxhkd"
        fi
    fi
fi

# --- Test ---

echo ""
echo "=== Testing ==="
curl -s -X POST "http://127.0.0.1:${PORT}/speak" \
    -H "Content-Type: application/json" \
    -d '{"text": "Claude Code TTS is ready. You can say read that to me to hear any response."}' \
    --max-time 15 \
    2>/dev/null | ffplay -nodisp -autoexit -loglevel quiet -i pipe:0 2>/dev/null

echo ""
echo "=== Installation complete ==="
echo ""
echo "Usage:"
echo "  On-demand:  Tell Claude 'read that to me'"
echo "  Auto mode:  Tell Claude 'voice on' (or set CLAUDE_TTS=auto)"
echo "  Plan mode:  Plans are automatically read aloud on approval prompt"
echo "  Stop:       Tell Claude 'voice off' (or set CLAUDE_TTS=off)"
echo ""
if [[ "$PLATFORM" == "Darwin" ]]; then
    echo "Daemon: launchctl start/stop com.$(whoami).kokoro-tts"
elif [[ "$PLATFORM" == "Linux" ]]; then
    echo "Daemon: systemctl --user start/stop kokoro-tts"
fi
echo "Logs:   /tmp/kokoro-tts.log"
echo ""
echo "MCP server (optional — lets Claude call TTS directly as a tool):"
echo "  Add to ~/.claude/settings.json under \"mcpServers\":"
echo "    \"tts\": {"
echo "      \"command\": \"${INSTALL_DIR}/venv/bin/python3\","
echo "      \"args\": [\"${INSTALL_DIR}/mcp-server.py\"]"
echo "    }"
