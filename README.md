# Claude Code TTS

Local, free text-to-speech for [Claude Code](https://claude.ai/code). Hear responses instead of reading them.

Uses [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) — an 82M parameter neural TTS model that runs entirely on your machine. No API keys, no cloud services, no cost.

https://github.com/user-attachments/assets/placeholder-demo-video

## Why

Reading long Claude Code responses — plans, research summaries, explanations — causes attention fatigue. Voice output lets you listen while keeping your eyes on code, or step away from the screen entirely.

The default mode is **silent**. You ask Claude to "read that to me" when you want it. No surprise audio.

## Features

- **On-demand** — say "read that to me" and Claude speaks its last response
- **Auto-speak sessions** — say "voice on" for hands-free mode (speaks questions, completions, errors; stays silent during code)
- **Plan reader** — automatically reads plans aloud at the approval prompt, where you can't type commands
- **Developer-aware** — pronounces acronyms correctly (API, CLI, JWT, OAuth), expands units (15ms → "15 milliseconds"), skips code blocks
- **Customizable** — edit `pronunciation.json` to change how any term is spoken
- **Long-form** — long responses are chunked into seamless audio with natural pacing
- **Zero cost** — runs 100% locally on your machine

## Requirements

- macOS or Linux
- Python 3.10+
- `jq` and `ffmpeg`
- ~340MB disk space (model files)
- [Claude Code](https://claude.ai/code)

### Installing dependencies

**macOS:**
```bash
brew install jq ffmpeg python@3.13
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt install jq ffmpeg python3.12 python3.12-venv
```

## Install

```bash
git clone https://github.com/mpaarating/claude-code-tts.git
cd claude-code-tts
bash install.sh
```

The installer:
1. Creates a Python venv and installs Kokoro
2. Downloads model files (~340MB one-time download)
3. Installs the TTS daemon (launchd on macOS, systemd on Linux)
4. Copies hooks and scripts to `~/.claude/`
5. Plays a test sentence to verify

After installing, add the hooks to `~/.claude/settings.json` (the installer prints the exact JSON).

### Hook configuration

Add to your `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [{
          "type": "command",
          "command": "bash ~/.claude/hooks/tts-speak.sh",
          "timeout": 15
        }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "ExitPlanMode",
        "hooks": [{
          "type": "command",
          "command": "bash ~/.claude/hooks/tts-plan-reader.sh",
          "timeout": 5
        }]
      }
    ]
  }
}
```

### Teaching Claude about voice

Add to your `~/.claude/CLAUDE.md`:

```markdown
## Voice Output (Kokoro TTS)

**On-demand**: When the user says "read that to me", "say that", "speak", or similar:
\`\`\`bash
bash ~/.claude/scripts/tts-speak.sh "text to speak"
\`\`\`
The script handles chunking and seamless playback. Runs locally, free.

**Stop playback**: When the user says "stop", "mute", or "quiet":
\`\`\`bash
bash ~/.claude/scripts/tts-stop.sh
\`\`\`

**Session voice toggle**: "voice on" / "voice off":
\`\`\`bash
export CLAUDE_TTS=auto   # auto-speak conversational responses
export CLAUDE_TTS=off    # back to silent
\`\`\`
```

## Usage

### On-demand (default)

Tell Claude to read something:

> "Read that to me"

> "Say that"

Claude pipes its response through TTS. Short responses play immediately; long responses are chunked with natural pacing — no gaps between sentences.

### Stop playback

Interrupt audio at any time:

> "Stop"

> "Mute"

Or directly: `bash ~/.claude/scripts/tts-stop.sh`

New audio automatically interrupts any currently playing audio — you don't need to stop manually before asking Claude to read something else.

### Voice sessions

Enable auto-speak for the current session:

> "Voice on"

> "Let's make this a voice session"

In auto mode, Claude speaks conversational responses and stays silent during code output. The "colleague in the room" model — speaks up when it matters, stays quiet when it doesn't.

Disable:

> "Voice off"

> "Mute"

### Plan reader

When Claude exits plan mode and presents a plan for approval, the plan is automatically read aloud. This matters because the approval prompt only has accept/reject — you can't type "read that to me."

## How it works

```
                         ┌──────────────────────────┐
  "Read that to me"      │     Kokoro TTS Daemon     │
  ───────────────────>   │     localhost:7723         │
  Claude Code hooks      │                           │
  send text via curl     │  ┌─────────┐ ┌─────────┐ │      ┌─────────┐
                         │  │preprocess│→│ Kokoro  │─┼──>   │ ffplay  │
                         │  │  .py     │ │  ONNX   │ │ WAV  │(playback│
                         │  └─────────┘ └─────────┘ │      └─────────┘
                         └──────────────────────────┘
```

**Daemon** — a Python HTTP server that keeps the 82M Kokoro model loaded in memory. No cold start per request.

**Preprocessing** — before text reaches Kokoro, it passes through a pipeline that:
- Strips code blocks, inline code, URLs, file paths, markdown formatting
- Expands acronyms (API → "A P I", JSON → "jason", kubectl → "kube control")
- Expands units (15ms → "15 milliseconds", 200MB → "200 megabytes")
- Splits camelCase and snake_case identifiers
- Verbalizes operators (=> → "arrow", && → "and")
- Strips emoji

**Chunking** — long text is split on sentence boundaries (~500 chars per chunk), generated separately, then concatenated with 150ms breath pauses into a single seamless WAV stream.

**Playback** — audio streams directly from curl to ffplay via pipe. No temp files touch disk.

## Configuration

### Environment variables

Set in the launchd plist, systemd service, or your shell:

| Variable | Default | Description |
|----------|---------|-------------|
| `KOKORO_PORT` | `7723` | Daemon listen port |
| `KOKORO_VOICE` | `af_heart` | Voice ID ([available voices](https://github.com/thewh1teagle/kokoro-onnx#voices)) |
| `KOKORO_SPEED` | `1.0` | Speech speed (0.5 = slow, 2.0 = fast) |
| `CLAUDE_TTS` | `off` | `off` (silent), `auto` (speak conversational responses), `on` (speak everything) |

### Custom pronunciations

Edit `~/.local/share/claude-code-tts/pronunciation.json` to change how terms are spoken:

```json
{
  "pronunciation": {
    "API": "A P I",
    "SQL": "sequel",
    "GIF": "jiff",
    "your-internal-tool": "your tool name"
  },
  "units": {
    "ms": "milliseconds",
    "req": "requests"
  },
  "symbols": [
    ["=>", " arrow "],
    ["&&", " and "]
  ]
}
```

Restart the daemon after editing. The server falls back to built-in defaults for any keys not in your config.

### Voices

Kokoro ships with multiple voices. Change the default by setting `KOKORO_VOICE`:

| Voice ID | Description |
|----------|-------------|
| `af_heart` | Female, warm (default) |
| `af_bella` | Female, clear |
| `am_adam` | Male, neutral |
| `am_michael` | Male, deep |

Full list: [kokoro-onnx voices](https://github.com/thewh1teagle/kokoro-onnx#voices)

## API

The daemon runs on `localhost:7723` and exposes:

### `POST /speak`

Generate speech from text. Auto-detects short vs long text and chunks accordingly.

```bash
curl -s -X POST http://localhost:7723/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world"}' \
  | ffplay -nodisp -autoexit -loglevel quiet -i pipe:0
```

**Request body:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `text` | string | required | Text to speak |
| `voice` | string | `af_heart` | Voice ID |
| `speed` | float | `1.0` | Speed multiplier |
| `mode` | string | `"auto"` | `"auto"` (full text) or `"summary"` (first 3 sentences) |

### `GET /health`

```bash
curl http://localhost:7723/health
# {"status": "ok", "model_loaded": true}
```

## Resource usage

| State | CPU | Memory |
|-------|-----|--------|
| Idle | 0% | ~935MB (loaded model) |
| Generating | ~200% for 1-2s | ~935MB |

The daemon runs at nice priority 10 — it yields to your foreground apps. The CPU spike during generation is brief (~1-2s per sentence on Apple Silicon) and won't interfere with Claude Code, Chrome, or other work.

## Project structure

```
claude-code-tts/
├── server/
│   ├── kokoro-server.py      # HTTP daemon (168 lines)
│   ├── preprocess.py          # Text normalization for TTS (267 lines)
│   └── pronunciation.json     # Customizable pronunciation maps
├── hooks/
│   ├── tts-speak.sh           # Claude Code Stop hook (auto-speak)
│   └── tts-plan-reader.sh     # Plan approval auto-reader
├── scripts/
│   ├── tts-speak.sh           # On-demand "read that to me"
│   └── tts-stop.sh            # Stop current audio playback
├── install.sh                 # One-command installer (macOS + Linux)
└── uninstall.sh               # Clean removal
```

## Daemon management

**macOS:**
```bash
launchctl start com.$(whoami).kokoro-tts   # start
launchctl stop com.$(whoami).kokoro-tts    # stop
launchctl unload ~/Library/LaunchAgents/com.$(whoami).kokoro-tts.plist  # disable
```

**Linux:**
```bash
systemctl --user start kokoro-tts    # start
systemctl --user stop kokoro-tts     # stop
systemctl --user disable kokoro-tts  # disable
```

**Logs:** `/tmp/kokoro-tts.log`

## Uninstall

```bash
bash uninstall.sh
```

Then manually remove the TTS hooks from `~/.claude/settings.json` and the Voice Output section from `~/.claude/CLAUDE.md`.

## Credits

- [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) by hexgrad — the TTS model
- [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) by thewh1teagle — ONNX runtime wrapper

## License

MIT
