# Claude Code TTS

Local, free text-to-speech for [Claude Code](https://claude.ai/code). Hear responses instead of reading them.

Uses [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) — an 82M parameter neural TTS model that runs entirely on your machine. No API keys, no cloud services, no cost.

## What it does

- **"Read that to me"** — tell Claude to read any response aloud, on demand
- **Voice sessions** — say "voice on" for auto-speak mode (questions, completions, errors spoken automatically; code output stays silent)
- **Plan reader** — plans are automatically read aloud when presented for approval, so you can listen instead of reading a wall of text
- **Long-form support** — long responses are chunked and concatenated into seamless audio with natural pacing

## Requirements

- macOS (uses launchd for the daemon)
- Python 3.10+
- `jq` and `ffmpeg` (`brew install jq ffmpeg`)
- ~340MB disk space (model files)
- Claude Code

## Install

```bash
git clone https://github.com/yourusername/claude-code-tts.git
cd claude-code-tts
bash install.sh
```

The installer will:
1. Create a Python venv and install dependencies
2. Download the Kokoro model files (~340MB)
3. Install the TTS daemon as a LaunchAgent (auto-starts on login)
4. Install Claude Code hooks and scripts
5. Run a test to verify everything works

After installing, add the hooks to your `~/.claude/settings.json` (the installer prints the exact config).

## Usage

### On-demand (default)

Just tell Claude to read something:

> "Read that to me"
> "Say that"
> "Speak"

Claude will pipe its last response through TTS. Works for short and long responses — long text is chunked with natural pacing.

### Auto-speak mode

Tell Claude to enable voice for the session:

> "Voice on"
> "Let's make this a voice session"

In auto mode, Claude speaks conversational responses (questions, completions, errors) and stays silent during code output, file edits, and tool results.

Turn it off:

> "Voice off"
> "Mute"

### Plan reader

When Claude presents a plan for approval (ExitPlanMode), the plan is automatically read aloud. This is useful because the approval prompt doesn't let you type commands — you can only accept or reject.

## Architecture

```
┌─────────────┐     POST /speak      ┌──────────────────┐
│  Claude Code │ ──────────────────── │  Kokoro Daemon    │
│  Stop Hook   │     or /speak-long   │  (localhost:7723) │
└─────────────┘                       └──────────────────┘
                                             │
                                      ┌──────┴──────┐
                                      │ Kokoro ONNX │
                                      │ (82M model) │
                                      └─────────────┘
                                             │
                                        WAV stream
                                             │
                                      ┌──────┴──────┐
                                      │   ffplay    │
                                      │  (playback) │
                                      └─────────────┘
```

- **Daemon** keeps the model loaded in memory (~935MB RSS) so there's no load time per request
- **Generation** takes ~1-2s for a sentence on Apple Silicon
- **Nice priority** (10) so it doesn't compete with your other apps
- **Streaming** — audio pipes directly to ffplay, no temp files

## Configuration

Environment variables (set in the launchd plist or shell):

| Variable | Default | Description |
|----------|---------|-------------|
| `KOKORO_PORT` | `7723` | Daemon port |
| `KOKORO_VOICE` | `af_heart` | Voice ID ([list](https://github.com/thewh1teagle/kokoro-onnx#voices)) |
| `KOKORO_SPEED` | `1.0` | Speech speed multiplier |
| `CLAUDE_TTS` | `off` | `off`, `auto`, or `on` |

## API

The daemon exposes two endpoints:

**`POST /speak`** — short text, single WAV response
```bash
curl -s -X POST http://localhost:7723/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world"}' | ffplay -nodisp -autoexit -loglevel quiet -i pipe:0
```

**`POST /speak-long`** — long text, chunked + concatenated into seamless WAV
```bash
curl -s -X POST http://localhost:7723/speak-long \
  -H "Content-Type: application/json" \
  -d '{"text": "Long text here..."}' | ffplay -nodisp -autoexit -loglevel quiet -i pipe:0
```

**`GET /health`** — daemon health check

## Uninstall

```bash
bash uninstall.sh
```

## Credits

- [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) by hexgrad
- [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) by thewh1teagle
