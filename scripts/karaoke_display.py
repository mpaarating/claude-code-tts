#!/usr/bin/env python3
"""Karaoke display engine — word-by-word terminal highlighting synchronized to TTS audio.

Reads display text from stdin. Duration passed via --duration flag.
Uses only Python stdlib (no external dependencies).

Usage:
    echo "text to highlight" | python3 karaoke_display.py --duration 4.5
"""

import argparse
import atexit
import shutil
import signal
import sys
import time

# ANSI escape sequences
DIM = "\033[2m"
BOLD_CYAN = "\033[1;36m"
RESET = "\033[0m"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
CLEAR_LINE = "\r\033[K"

# Minimum seconds any single word can occupy (prevents zero-width flicker)
MIN_WORD_DURATION = 0.08
# Minimum character weight per word (so "I" and "a" still get some time)
MIN_CHAR_WEIGHT = 2
# Display refresh interval in seconds (~33 fps)
REFRESH_INTERVAL = 0.03

# Output target — /dev/tty bypasses stdout redirection (works under MCP)
_tty = None


def _get_output():
    """Open /dev/tty for direct terminal output, fall back to stderr."""
    global _tty
    if _tty is not None:
        return _tty
    try:
        _tty = open("/dev/tty", "w")
    except OSError:
        _tty = sys.stderr
    return _tty


def _write(text):
    """Write text to the terminal output."""
    out = _get_output()
    out.write(text)
    out.flush()


def _cleanup(sig=None, frame=None):
    """Reset terminal state: show cursor, clear ANSI attributes."""
    try:
        _write(SHOW_CURSOR + RESET + "\n")
        if _tty is not None and _tty is not sys.stderr:
            _tty.close()
    except Exception:
        pass
    if sig is not None:
        sys.exit(0)


def compute_word_timings(words, total_duration):
    """Return per-word durations proportional to character count.

    Longer words get more time. Each word has a minimum character weight
    of MIN_CHAR_WEIGHT so short words ("I", "a") still get some time.
    Per-word duration is floored at MIN_WORD_DURATION seconds.
    The sum of returned durations always equals total_duration.
    """
    if not words:
        return []
    if total_duration <= 0:
        return [0.0] * len(words)

    n = len(words)
    char_weights = [max(len(w), MIN_CHAR_WEIGHT) for w in words]
    total_weight = sum(char_weights)

    # Initial proportional allocation
    timings = [(w / total_weight) * total_duration for w in char_weights]

    # Enforce minimum duration floor
    deficit = 0.0
    unclamped_weight = 0.0
    for i, t in enumerate(timings):
        if t < MIN_WORD_DURATION:
            deficit += MIN_WORD_DURATION - t
            timings[i] = MIN_WORD_DURATION
        else:
            unclamped_weight += char_weights[i]

    # Redistribute deficit from unclamped words proportionally
    if deficit > 0 and unclamped_weight > 0:
        for i in range(n):
            if timings[i] > MIN_WORD_DURATION:
                reduction = deficit * (char_weights[i] / unclamped_weight)
                timings[i] -= reduction

    # Fix floating-point drift so sum exactly equals total_duration
    drift = total_duration - sum(timings)
    if timings:
        timings[-1] += drift

    return timings


def render_line(words, current_idx, term_width):
    """Build one ANSI-formatted line showing a sliding window of words.

    - Words before current_idx: dim
    - Word at current_idx: bold cyan
    - Words after current_idx: default
    - Sliding window centered on current word, fits within term_width
    - Appends progress: [42%] in dim
    """
    n = len(words)
    progress = f" {DIM}[{(current_idx + 1) * 100 // n}%]{RESET}"
    # Reserve space for progress indicator (strip ANSI for width calc)
    progress_width = len(f" [{(current_idx + 1) * 100 // n}%]")
    available = term_width - progress_width - 2  # margin

    # Expand window around current_idx to fill available width
    left = current_idx
    right = current_idx
    width = len(words[current_idx])

    while True:
        expanded = False
        # Try expanding left
        if left > 0 and width + len(words[left - 1]) + 1 <= available:
            left -= 1
            width += len(words[left]) + 1
            expanded = True
        # Try expanding right
        if right < n - 1 and width + len(words[right + 1]) + 1 <= available:
            right += 1
            width += len(words[right]) + 1
            expanded = True
        if not expanded:
            break

    # Build the formatted line
    parts = []
    for i in range(left, right + 1):
        if i < current_idx:
            parts.append(f"{DIM}{words[i]}{RESET}")
        elif i == current_idx:
            parts.append(f"{BOLD_CYAN}{words[i]}{RESET}")
        else:
            parts.append(words[i])

    return CLEAR_LINE + " ".join(parts) + progress


def run(words, timings):
    """Main display loop. Blocks until all words are shown."""
    n = len(words)
    term_width = shutil.get_terminal_size().columns

    word_idx = 0
    # Cumulative timestamps: word i ends at cumulative[i]
    cumulative = []
    acc = 0.0
    for t in timings:
        acc += t
        cumulative.append(acc)

    t0 = time.monotonic()

    while word_idx < n:
        elapsed = time.monotonic() - t0

        # Advance to the correct word based on elapsed time
        while word_idx < n - 1 and elapsed >= cumulative[word_idx]:
            word_idx += 1

        _write(render_line(words, word_idx, term_width))
        time.sleep(REFRESH_INTERVAL)

    # Show final state briefly
    _write(render_line(words, n - 1, term_width))
    time.sleep(0.2)
    _write(CLEAR_LINE)


def main():
    parser = argparse.ArgumentParser(description="Karaoke word-highlighting display")
    parser.add_argument("--duration", type=float, required=True, help="Audio duration in seconds")
    parser.add_argument("--width", type=int, default=0, help="Override terminal width")
    args = parser.parse_args()

    text = sys.stdin.read().strip()
    if not text:
        sys.exit(0)

    words = text.split()
    if not words:
        sys.exit(0)

    timings = compute_word_timings(words, args.duration)

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)
    atexit.register(_cleanup)

    _write(HIDE_CURSOR)
    run(words, timings)
    _cleanup()


if __name__ == "__main__":
    main()
