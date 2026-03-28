# Contributing

Thanks for your interest in claude-code-tts!

## Quick start

```bash
git clone https://github.com/mpaarating/claude-code-tts.git
cd claude-code-tts
bash install.sh
```

## Running tests

Tests use pytest against the preprocessing module:

```bash
# Using the installed venv
~/.local/share/claude-code-tts/venv/bin/python -m pytest tests/ -v

# Or with any Python 3.10+ that has pytest
python -m pytest tests/ -v
```

Tests don't require Kokoro or the daemon running — they only test text preprocessing.

## Adding pronunciations

The easiest way to contribute is adding developer terms to the pronunciation map.

1. Edit `server/pronunciation.json`
2. Add your term to the appropriate section (`pronunciation`, `units`, or `symbols`)
3. Add a test case in `tests/test_preprocess.py`
4. Run tests to verify
5. Submit a PR

### Guidelines for pronunciations
- Use word boundaries — terms are matched with `\b` regex boundaries
- Case matters: `"API"` matches `API` but not `api`
- Spell out acronyms with spaces: `"A P I"` not `"ay pee eye"`
- For units, expand to the full word: `"ms"` → `"milliseconds"`
- Test with the actual TTS to make sure it sounds right:
  ```bash
  curl -s -X POST http://localhost:7723/speak \
    -H "Content-Type: application/json" \
    -d '{"text": "Your test sentence with the NEW_TERM here"}' \
    | ffplay -nodisp -autoexit -loglevel quiet -f wav -window_title claude-tts -i pipe:0
  ```

## Project structure

```
server/
  kokoro-server.py    — HTTP daemon (thin: routing + audio generation)
  preprocess.py       — Text normalization (where most logic lives)
  pronunciation.json  — Customizable pronunciation maps
hooks/                — Claude Code hook scripts
scripts/              — User-facing scripts (speak, stop)
tests/                — pytest tests for preprocessing
install.sh            — Installer (macOS + Linux)
```

## Submitting changes

1. Fork the repo
2. Create a feature branch (`feat/your-feature` or `fix/your-fix`)
3. Make your changes
4. Run tests: `python -m pytest tests/ -v`
5. Submit a PR

Keep PRs focused — one feature or fix per PR.
