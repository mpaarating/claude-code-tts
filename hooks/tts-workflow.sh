#!/bin/bash
# Claude Code TTS — PostToolUse hook for workflow notifications.
# Speaks summaries of build/test/deploy results after Bash commands.
#
# Triggers on recognized commands: test runners, build tools, git push.
# Uses summary mode so messages are brief.

KOKORO_URL="http://127.0.0.1:${KOKORO_PORT:-7723}"
CHIME_SCRIPT="${HOME}/.claude/scripts/tts-chime.sh"

HOOK_JSON=$(cat)
TOOL_NAME=$(echo "$HOOK_JSON" | jq -r '.tool_name // empty' 2>/dev/null)

[[ "$TOOL_NAME" != "Bash" ]] && exit 0

TOOL_INPUT=$(echo "$HOOK_JSON" | jq -r '.tool_input.command // empty' 2>/dev/null)
TOOL_OUTPUT=$(echo "$HOOK_JSON" | jq -r '.tool_output // empty' 2>/dev/null)

[[ -z "$TOOL_INPUT" ]] && exit 0

# --- Match recognized commands ---

SUMMARY=""

# Test runners
if echo "$TOOL_INPUT" | grep -qE '(npm test|pnpm test|yarn test|pytest|jest|vitest|cargo test|go test|rspec)'; then
    if echo "$TOOL_OUTPUT" | grep -qiE '(passed|success|ok)'; then
        PASS_COUNT=$(echo "$TOOL_OUTPUT" | grep -oE '[0-9]+ passed' | head -1)
        SUMMARY="Tests passed${PASS_COUNT:+, $PASS_COUNT}."
        TONE="completion"
    elif echo "$TOOL_OUTPUT" | grep -qiE '(failed|error|failure)'; then
        FAIL_COUNT=$(echo "$TOOL_OUTPUT" | grep -oE '[0-9]+ failed' | head -1)
        SUMMARY="Tests failed${FAIL_COUNT:+, $FAIL_COUNT}."
        TONE="error"
    fi

# Build / type check
elif echo "$TOOL_INPUT" | grep -qE '(tsc|pnpm build|npm run build|yarn build|cargo build|make|go build)'; then
    if echo "$TOOL_OUTPUT" | grep -qiE '(error|failed)'; then
        ERROR_COUNT=$(echo "$TOOL_OUTPUT" | grep -cE '(error TS|Error:)' || true)
        SUMMARY="Build failed${ERROR_COUNT:+ with $ERROR_COUNT errors}."
        TONE="error"
    else
        SUMMARY="Build succeeded."
        TONE="completion"
    fi

# Git push
elif echo "$TOOL_INPUT" | grep -qE 'git push'; then
    if echo "$TOOL_OUTPUT" | grep -qiE '(rejected|error|failed)'; then
        SUMMARY="Push rejected."
        TONE="error"
    else
        BRANCH=$(echo "$TOOL_OUTPUT" | grep -oE '[^ ]+ -> [^ ]+' | head -1)
        SUMMARY="Pushed${BRANCH:+ $BRANCH}."
        TONE="completion"
    fi

# Lint
elif echo "$TOOL_INPUT" | grep -qE '(eslint|ruff|pylint|clippy)'; then
    if echo "$TOOL_OUTPUT" | grep -qiE '(error|warning)'; then
        SUMMARY="Linter found issues."
        TONE="warning"
    else
        SUMMARY="Lint clean."
        TONE="completion"
    fi
fi

[[ -z "$SUMMARY" ]] && exit 0

# --- Play chime + speak summary ---

curl -s --max-time 1 "$KOKORO_URL/health" >/dev/null 2>&1 || exit 0

(
    if [[ -n "$TONE" && -x "$CHIME_SCRIPT" ]]; then
        bash "$CHIME_SCRIPT" "$TONE"
        sleep 0.3
    fi

    curl -s -X POST "$KOKORO_URL/speak" \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg text "$SUMMARY" '{text: $text}')" \
        --max-time 10 \
        2>/dev/null | ffplay -nodisp -autoexit -loglevel quiet -f wav -window_title claude-tts -i pipe:0 2>/dev/null
) &

exit 0
