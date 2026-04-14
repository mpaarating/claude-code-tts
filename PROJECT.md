# Project: claude-code-tts

## Problem Statement

Reading long Claude Code responses — plans, research, explanations — causes attention fatigue. Voice output lets developers listen while keeping their eyes on code, or step away entirely. Kokoro TTS runs 100% locally with zero cost.

## Success Criteria

- [x] On-demand and auto-speak modes working
- [x] Streaming audio with <300ms first-word latency
- [x] Multi-agent voice routing and emotion/tone awareness
- [x] Installer handles full setup without manual JSON editing
- [x] Voice-controlled session settings (speed, volume)
- [x] Content-aware hooks for diffs and errors

## Phases

### Shipped
Core TTS pipeline, streaming, multi-agent voices, emotion routing, conversation history, workflow notifications, MCP server, smart activation, chimes, hotkeys, karaoke mode, CI/tests, repo security hardening, permissions docs.

### Next
Installer auto-config, error summarization hook, volume/speed voice control, diff narration.

### Later / Icebox
- Bidirectional voice (STT + TTS) — #11
- Voice cloning from audio sample — #10
- Quiet hours / DND mode
- Audio output device selection
- PR review narration
- Windows/WSL support
- Fallback to system TTS
- Health check command
- Pronunciation community file
- Require signed commits
- Dependabot config

## Backlog

| # | Feature | Priority | Phase | Status | Notes |
|---|---------|----------|-------|--------|-------|
| 1 | Installer auto-configures settings.json | P1 | Next | done | jq merge into existing settings.json, atomic write, --no-hooks opt-out |
| 2 | Error summarization hook | P1 | Next | done | Generic catch-all in tts-workflow.sh for non-zero exit codes on unrecognized commands |
| 3 | Volume/speed control via voice | P1 | Next | done | KOKORO_SPEED + KOKORO_VOLUME env vars, passed through all scripts/hooks to daemon and ffplay |
| 4 | Diff narration | P2 | Next | done | Extracts file names from diff headers or stat summary line, speaks concise summary |
| 5 | Bidirectional voice (STT + TTS) | P2 | Later | not started | GitHub #11 — ambitious |
| 6 | Voice cloning | P2 | Later | not started | GitHub #10 — ambitious |
| 7 | Require signed commits | P2 | Later | not started | Repo security |
| 8 | Dependabot config | P2 | Later | not started | Dependency security alerts |

## Research Questions

- [x] Can the installer safely merge hook config into an existing settings.json without clobbering other settings? (jq merge strategy) — Yes, `jq += []` appends safely
- [x] What's the best UX for voice-controlled speed/volume — env var, daemon endpoint, or both? — Env vars (KOKORO_SPEED, KOKORO_VOLUME) passed through to daemon/ffplay. No new endpoints needed.
- [x] For diff narration, should the hook trigger on `git diff` output or on commit/PR events? — Triggers on `git diff/log/show` commands in tts-workflow.sh, extracts file names or stat summary

## Key Decisions

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-14 | Repo security hardening complete | Branch protection, CODEOWNERS, CI checks all active |
| 2026-04-14 | Dropped bash prefix from scripts | Enables granular permission whitelisting in Claude Code |
| 2026-04-14 | Four new features added to backlog | User feedback + brainstorm: installer auto-config, error hook, voice control, diff narration |
| 2026-04-14 | Installer auto-config implemented | jq merge with atomic write, confirmation prompt, --no-hooks flag, pre-validation of existing JSON |
| 2026-04-14 | Error summarization added to workflow hook | Extended tts-workflow.sh with generic catch-all for non-zero exit codes |
| 2026-04-14 | Speed/volume control implemented | KOKORO_SPEED and KOKORO_VOLUME env vars threaded through all 4 scripts/hooks |
| 2026-04-14 | Diff narration implemented (Option A) | Simple file name extraction from diff headers + stat line fallback. Can upgrade to semantic summaries later. |
