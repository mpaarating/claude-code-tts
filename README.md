# Claude Code TTS

[![Tests](https://github.com/mpaarating/claude-code-tts/actions/workflows/test.yml/badge.svg)](https://github.com/mpaarating/claude-code-tts/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

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

The installer will offer to configure hooks in `~/.claude/settings.json` automatically. Pass `--no-hooks` to skip and configure manually.

### Hook configuration

Add to your `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [{
          "type": "command",
          "command": "~/.claude/hooks/tts-speak.sh",
          "timeout": 15
        }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "ExitPlanMode",
        "hooks": [{
          "type": "command",
          "command": "~/.claude/hooks/tts-plan-reader.sh",
          "timeout": 5
        }]
      }
    ]
  }
}
```

### Permissions

When Claude speaks on-demand, it runs the TTS scripts via the Bash tool. Rather than whitelisting all bash commands, you can allow just the specific scripts in your `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "Bash(~/.claude/scripts/tts-speak.sh:*)",
      "Bash(~/.claude/scripts/tts-stop.sh:*)"
    ]
  }
}
```

The scripts are installed as executable, so no `bash` prefix is needed.

### Teaching Claude about voice

Add to your `~/.claude/CLAUDE.md`:

```markdown
## Voice Output (Kokoro TTS)

**On-demand**: When the user says "read that to me", "say that", "speak", or similar:
\`\`\`bash
~/.claude/scripts/tts-speak.sh "text to speak"
\`\`\`
The script handles chunking and seamless playback. Runs locally, free.

**Stop playback**: When the user says "stop", "mute", or "quiet":
\`\`\`bash
~/.claude/scripts/tts-stop.sh
\`\`\`

**Session voice toggle**: "voice on" / "voice off":
\`\`\`bash
export CLAUDE_TTS=auto   # auto-speak conversational responses
export CLAUDE_TTS=off    # back to silent
\`\`\`

**Speed/volume**: "speak slower", "speak faster", "louder", "quieter":
\`\`\`bash
export KOKORO_SPEED=0.8   # slower (range: 0.5 to 2.0, default 1.0)
export KOKORO_SPEED=1.3   # faster
export KOKORO_VOLUME=60   # quieter (range: 0 to 100, default 100)
export KOKORO_VOLUME=100  # full volume
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

Or directly: `~/.claude/scripts/tts-stop.sh`

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
- Expands acronyms (API → "eh P I", JSON → "jason", kubectl → "kube control")
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
| `KOKORO_VOLUME` | `100` | Playback volume (0 = mute, 100 = full) |
| `CLAUDE_TTS` | `off` | `off` (silent), `auto` (speak conversational responses), `on` (speak everything) |

### Custom pronunciations

Two files control how terms are spoken, both next to the server in `~/.local/share/claude-code-tts/`:

- `pronunciation.json` is the shared table that ships with the repo. The installer refreshes it on every run, so don't edit it in place; change `server/pronunciation.json` in the repo instead (and keep it in sync with the built-in defaults in `preprocess.py`; a test enforces this).
- `pronunciation.local.json` is yours. The installer creates it empty and never touches it again. Anything in it is merged on top of the shared table: dict keys override, lists append. Put team names, internal services, and ticket-prefix quirks here.

```json
{
  "pronunciation": {
    "proofapi": "proof eh P I",
    "your-internal-tool": "your tool name"
  },
  "acronym_words": ["SCARS"]
}
```

Supported sections: `pronunciation` (exact tokens, case-sensitive), `units` (`ms` -> `milliseconds`), `symbols` (ordered `[from, to]` pairs), `abbreviations` (`e.g.` -> `for example`), `acronym_words` (all-caps tokens to read as words), `tone_voices`, `agent_voices`.

Restart the daemon after editing either file.

#### What the preprocessor does on its own

Beyond the table, `preprocess.py` rewrites the patterns espeak gets wrong:

| Written | Spoken |
|---------|--------|
| `SFT-1141`, `!249`, `#12` | S F T eleven forty-one, M R two forty-nine, number twelve |
| `#wg-software-factory` | the wg software factory channel |
| `9/15`, `2026-09-16` | September 15th (year added only when it isn't this year) |
| `9:44pm`, `1:1` | nine forty-four P M, one on one |
| `EOD`, `DRI`, `PTO` | spelled out: any 2-5 letter all-caps token that isn't in the system dictionary |
| `` `glab mr view 252` `` | spoken (short inline code is kept); long or path-like inline code is dropped |
| `~/.claude/hooks/x.sh:12` | x dot sh |
| `e.g.`, `3.13`, `~2hrs`, em dash | for example, three point thirteen, about two hours, a comma pause |

A standalone letter A is emitted as "eh" because espeak otherwise reads it as the article.

#### Checking what will be said

```bash
~/.claude/scripts/tts-speak.sh --dry-run "Merge MR !249 for SFT-910 by EOD"
# would_speak: true  tone: none
# Merge M R 2 49 for S F T 9 10 by E O D

~/.claude/scripts/tts-speak.sh --dry-run --summary "$(cat response.md)"   # through the auto-speak summarizer
```

The same data is available from the daemon directly: `POST /preprocess` with `{"text": "...", "mode": "summary"}`.

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
