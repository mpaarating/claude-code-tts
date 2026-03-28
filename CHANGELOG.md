# Changelog

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
