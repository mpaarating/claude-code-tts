# Changelog

## [Unreleased]

### Changed
- Audio is streamed sentence by sentence: playback starts after the first sentence is synthesized (about 0.5-0.8 s) instead of after the whole response (2-4 s). Stopping playback stops synthesis.
- Auto-speak summaries stop at the end of the opening paragraph. Headings, list intros, and footers below it are no longer read aloud.
- The Stop hook reads voice state from `~/.local/state/claude-tts/state` (written by `scripts/voice.sh`) instead of the `CLAUDE_TTS` env var, which never reached hooks. Speed, volume, and chime tones come from `~/.config/claude-code-tts/env`.
- Chimes play only for question, error, and warning tones by default (`TTS_CHIME_TONES`).
- A new response always interrupts the one still playing. The lock-file debounce, which never worked (it recorded an exited PID), is gone.
- Commit hashes and empty parentheses left by dropped inline code are removed before speaking.
- `X-TTS-Duration` response header removed (total length is unknown while streaming). History log gains `first_audio_ms` and `interrupted`.

## [0.1.0] - 2026-03-28

### Added
- Kokoro TTS daemon with persistent model loading
- On-demand TTS via `tts-speak.sh` ("read that to me")
- Auto-speak mode via Claude Code Stop hook
- Plan reader — auto-reads plans at approval prompt
- Developer-aware preprocessing: acronym expansion, unit expansion, camelCase/snake_case splitting, operator verbalization
- Customizable pronunciation via `pronunciation.json`
- Long-form chunking with seamless audio concatenation
- Summary mode for auto-speak hooks
- Audio interrupt via `tts-stop.sh`
- macOS (launchd) and Linux (systemd) support
- Installer and uninstaller scripts
