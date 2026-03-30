"""Tests for the karaoke display engine."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from karaoke_display import compute_word_timings, render_line


# ---------------------------------------------------------------------------
# compute_word_timings
# ---------------------------------------------------------------------------


class TestComputeWordTimings:
    def test_proportional_to_length(self):
        words = ["I", "fundamentally", "agree"]
        timings = compute_word_timings(words, 3.0)
        assert timings[1] > timings[0]
        assert timings[1] > timings[2]

    def test_sums_to_total(self):
        words = ["Hello", "world", "this", "is", "a", "test"]
        timings = compute_word_timings(words, 5.0)
        assert abs(sum(timings) - 5.0) < 0.001

    def test_single_word(self):
        timings = compute_word_timings(["Hello"], 2.0)
        assert len(timings) == 1
        assert abs(timings[0] - 2.0) < 0.001

    def test_minimum_duration_floor(self):
        words = ["I", "a", "supercalifragilisticexpialidocious"]
        timings = compute_word_timings(words, 3.0)
        assert timings[0] >= 0.08
        assert timings[1] >= 0.08

    def test_empty_input(self):
        assert compute_word_timings([], 5.0) == []

    def test_zero_duration(self):
        timings = compute_word_timings(["Hello", "world"], 0.0)
        assert all(t == 0.0 for t in timings)

    def test_equal_length_words_get_equal_time(self):
        words = ["aaa"] * 10
        timings = compute_word_timings(words, 10.0)
        assert abs(timings[0] - timings[5]) < 0.001
        assert abs(sum(timings) - 10.0) < 0.001

    def test_longest_word_gets_most_time(self):
        words = "The API uses JWT tokens for authentication".split()
        timings = compute_word_timings(words, 4.0)
        assert len(timings) == 7
        assert abs(sum(timings) - 4.0) < 0.001
        # "authentication" (14 chars) should get the most time
        assert timings[6] == max(timings)

    def test_short_words_use_minimum_weight(self):
        # "I" (1 char) and "is" (2 chars) should get the same weight
        # because both are at or below MIN_CHAR_WEIGHT of 2
        words = ["I", "is", "extraordinary"]
        timings = compute_word_timings(words, 3.0)
        assert abs(timings[0] - timings[1]) < 0.001

    def test_many_words(self):
        words = ["word"] * 100
        timings = compute_word_timings(words, 20.0)
        assert len(timings) == 100
        assert abs(sum(timings) - 20.0) < 0.001


# ---------------------------------------------------------------------------
# render_line
# ---------------------------------------------------------------------------


class TestRenderLine:
    def test_current_word_highlighted(self):
        words = ["Hello", "world", "test"]
        line = render_line(words, 1, 80)
        assert "\033[1;36mworld\033[0m" in line

    def test_past_words_dimmed(self):
        words = ["Hello", "world", "test"]
        line = render_line(words, 2, 80)
        assert "\033[2m" in line

    def test_progress_shown(self):
        words = ["Hello", "world"]
        line = render_line(words, 0, 80)
        assert "%" in line

    def test_first_word(self):
        words = ["Hello", "world"]
        line = render_line(words, 0, 80)
        assert "\033[1;36mHello\033[0m" in line

    def test_last_word(self):
        words = ["Hello", "world"]
        line = render_line(words, 1, 80)
        assert "\033[1;36mworld\033[0m" in line

    def test_narrow_terminal_does_not_crash(self):
        words = "This is a very long sentence with many words".split()
        line = render_line(words, 5, 30)
        assert len(line) > 0

    def test_single_word(self):
        words = ["Hello"]
        line = render_line(words, 0, 80)
        assert "\033[1;36mHello\033[0m" in line
        assert "100%" in line

    def test_progress_increases(self):
        words = ["one", "two", "three", "four"]
        line_start = render_line(words, 0, 80)
        line_end = render_line(words, 3, 80)
        assert "25%" in line_start
        assert "100%" in line_end
