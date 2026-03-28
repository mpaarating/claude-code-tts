#!/bin/bash
# Query TTS conversation history.
#
# Usage:
#   tts-log                     # last 20 entries
#   tts-log --today             # today's entries
#   tts-log --search "auth"     # search by content
#   tts-log --tail              # follow new entries
#   tts-log --stats             # summary stats

LOG_FILE="${HOME}/.local/share/claude-code-tts/logs/tts-history.jsonl"

if [[ ! -f "$LOG_FILE" ]]; then
    echo "No history yet. Speak something first."
    exit 0
fi

case "${1:-}" in
    --today)
        TODAY=$(date -u +"%Y-%m-%d")
        grep "\"$TODAY" "$LOG_FILE" | jq -r '[.timestamp, .tone // "—", .text[:80]] | join(" | ")'
        ;;
    --search)
        [[ -z "$2" ]] && { echo "Usage: tts-log --search <term>"; exit 1; }
        grep -i "$2" "$LOG_FILE" | jq -r '[.timestamp, .text[:80]] | join(" | ")'
        ;;
    --tail)
        tail -f "$LOG_FILE" | jq -r '[.timestamp, .tone // "—", .text[:60]] | join(" | ")'
        ;;
    --stats)
        TOTAL=$(wc -l < "$LOG_FILE" | tr -d ' ')
        TODAY_COUNT=$(grep "\"$(date -u +"%Y-%m-%d")" "$LOG_FILE" | wc -l | tr -d ' ')
        echo "Total spoken: $TOTAL"
        echo "Today: $TODAY_COUNT"
        echo ""
        echo "By tone:"
        jq -r '.tone // "default"' "$LOG_FILE" | sort | uniq -c | sort -rn
        echo ""
        echo "By voice:"
        jq -r '.voice // "unknown"' "$LOG_FILE" | sort | uniq -c | sort -rn
        ;;
    --help|-h)
        echo "Usage: tts-log [--today | --search <term> | --tail | --stats]"
        echo ""
        echo "  (no args)   Show last 20 entries"
        echo "  --today     Today's entries"
        echo "  --search    Search by content"
        echo "  --tail      Follow new entries live"
        echo "  --stats     Summary statistics"
        ;;
    *)
        tail -20 "$LOG_FILE" | jq -r '[.timestamp, .tone // "—", .voice, .text[:80]] | join(" | ")'
        ;;
esac
