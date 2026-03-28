"""Tests for the TTS preprocessing pipeline."""

import sys
import os

# Add server/ to path so we can import preprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from preprocess import classify_tone, preprocess, should_speak, split_sentences, summarize, voice_for_tone


# ---------------------------------------------------------------------------
# preprocess: acronym expansion
# ---------------------------------------------------------------------------

class TestAcronyms:
    def test_api(self):
        assert "A P I" in preprocess("The API is down")

    def test_cli(self):
        assert "C L I" in preprocess("Use the CLI tool")

    def test_json(self):
        assert "jason" in preprocess("Parse the JSON response")

    def test_jwt(self):
        assert "J W T" in preprocess("The JWT token expired")

    def test_sql(self):
        assert "sequel" in preprocess("Run a SQL query")

    def test_oauth(self):
        assert "oh auth" in preprocess("The OAuth flow failed")

    def test_kubectl(self):
        assert "kube control" in preprocess("Run kubectl apply")

    def test_nginx(self):
        assert "engine x" in preprocess("Configure nginx")

    def test_stdout_stderr(self):
        result = preprocess("Check stdout and stderr")
        assert "standard out" in result
        assert "standard error" in result

    def test_case_sensitivity(self):
        # "api" lowercase should not be expanded (word boundary + case-sensitive)
        result = preprocess("the api endpoint")
        # API is case-sensitive in the map, so lowercase "api" won't match
        assert "A P I" not in result


# ---------------------------------------------------------------------------
# preprocess: unit expansion
# ---------------------------------------------------------------------------

class TestUnits:
    def test_milliseconds(self):
        assert "15 milliseconds" in preprocess("adds 15ms of latency")

    def test_megabytes(self):
        assert "200 megabytes" in preprocess("uses 200MB of RAM")

    def test_gigabytes(self):
        assert "5 gigabytes" in preprocess("needs 5GB free")

    def test_seconds(self):
        assert "30 seconds" in preprocess("timeout after 30s")

    def test_gigahertz(self):
        assert "3 gigahertz" in preprocess("runs at 3GHz")


# ---------------------------------------------------------------------------
# preprocess: code stripping
# ---------------------------------------------------------------------------

class TestCodeStripping:
    def test_fenced_code_block(self):
        text = "Here is code:\n```python\nprint('hello')\n```\nThat's it."
        result = preprocess(text)
        assert "print" not in result
        assert "it" in result

    def test_inline_code_removed(self):
        text = "The `fetchUser` function returns a promise."
        result = preprocess(text)
        assert "fetchUser" not in result
        assert "fetch User" not in result
        assert "function" in result

    def test_multiple_code_blocks(self):
        text = "First:\n```\ncode1\n```\nMiddle.\n```\ncode2\n```\nEnd."
        result = preprocess(text)
        assert "code1" not in result
        assert "code2" not in result
        assert "Middle" in result


# ---------------------------------------------------------------------------
# preprocess: URL and path handling
# ---------------------------------------------------------------------------

class TestUrlsAndPaths:
    def test_url_replaced(self):
        result = preprocess("Visit https://example.com/docs for more")
        assert "U R L" in result
        assert "example.com" not in result

    def test_filepath_simplified(self):
        result = preprocess("Edit /src/components/Auth.tsx")
        assert "Auth" in result
        assert "/src/components/" not in result


# ---------------------------------------------------------------------------
# preprocess: markdown cleanup
# ---------------------------------------------------------------------------

class TestMarkdown:
    def test_bold_stripped(self):
        assert "important" in preprocess("This is **important**")
        assert "**" not in preprocess("This is **important**")

    def test_italic_stripped(self):
        assert "emphasis" in preprocess("Add *emphasis* here")
        assert "*" not in preprocess("Add *emphasis* here")

    def test_link_text_kept(self):
        result = preprocess("See [the docs](https://example.com) for details")
        assert "the docs" in result
        assert "example.com" not in result

    def test_header_stripped(self):
        result = preprocess("## Section Title\nContent here")
        assert "Section Title" in result
        assert "##" not in result

    def test_table_stripped(self):
        result = preprocess("Before\n| Col1 | Col2 |\n| a | b |\nAfter")
        assert "Col1" not in result
        assert "After" in result

    def test_blockquote_stripped(self):
        result = preprocess("> This is a quote")
        assert "This is a quote" in result
        assert ">" not in result


# ---------------------------------------------------------------------------
# preprocess: operators and symbols
# ---------------------------------------------------------------------------

class TestSymbols:
    def test_arrow(self):
        assert "arrow" in preprocess("map => value")

    def test_thin_arrow(self):
        assert "arrow" in preprocess("ptr -> field")

    def test_not_equal(self):
        assert "not equal to" in preprocess("a !== b")

    def test_double_equal(self):
        assert "equals" in preprocess("a == b")

    def test_and(self):
        assert " and " in preprocess("a && b")

    def test_or(self):
        assert " or " in preprocess("a || b")


# ---------------------------------------------------------------------------
# preprocess: camelCase and snake_case
# ---------------------------------------------------------------------------

class TestIdentifierSplitting:
    def test_camel_case(self):
        result = preprocess("Call fetchUserData next")
        assert "fetch User Data" in result

    def test_snake_case(self):
        result = preprocess("The user_name field")
        assert "user name" in result


# ---------------------------------------------------------------------------
# preprocess: version numbers
# ---------------------------------------------------------------------------

class TestVersionNumbers:
    def test_semver(self):
        result = preprocess("Upgrade to v2.1.3")
        assert "version 2 dot 1 dot 3" in result

    def test_major_minor(self):
        result = preprocess("Use v3.0")
        assert "version 3 dot 0" in result


# ---------------------------------------------------------------------------
# preprocess: file extensions
# ---------------------------------------------------------------------------

class TestFileExtensions:
    def test_dot_py(self):
        assert "dot py" in preprocess("Edit main.py")

    def test_dot_ts(self):
        assert "dot ts" in preprocess("Open index.ts")


# ---------------------------------------------------------------------------
# preprocess: emoji stripping
# ---------------------------------------------------------------------------

class TestEmoji:
    def test_emoji_removed(self):
        result = preprocess("Great work! 🎉🚀")
        assert "Great work" in result
        assert "🎉" not in result
        assert "🚀" not in result


# ---------------------------------------------------------------------------
# preprocess: whitespace normalization
# ---------------------------------------------------------------------------

class TestWhitespace:
    def test_paragraph_breaks(self):
        result = preprocess("First paragraph.\n\nSecond paragraph.")
        assert ". " in result  # double newline becomes sentence boundary

    def test_extra_spaces_collapsed(self):
        result = preprocess("Too   many    spaces")
        assert "  " not in result

    def test_empty_input(self):
        assert preprocess("") == ""
        assert preprocess("   ") == ""


# ---------------------------------------------------------------------------
# should_speak
# ---------------------------------------------------------------------------

class TestShouldSpeak:
    def test_normal_text(self):
        assert should_speak("Here is a normal response about your code.") is True

    def test_too_short(self):
        assert should_speak("OK") is False
        assert should_speak("") is False
        assert should_speak(None) is False

    def test_code_heavy_response(self):
        text = "Fix:\n```python\ndef foo():\n    pass\n\ndef bar():\n    pass\n\ndef baz():\n    return 1\n```"
        assert should_speak(text) is False

    def test_mixed_response_mostly_text(self):
        text = (
            "The issue is in the auth middleware.\n"
            "It skips token validation on retry.\n"
            "Here is the fix:\n"
            "```python\nif token.expired: raise AuthError\n```\n"
            "Let me know if that works.\n"
            "I also checked the tests."
        )
        assert should_speak(text) is True

    def test_exactly_at_threshold(self):
        # 40% code is the threshold — at exactly 40%, should still speak
        # 10 lines total, 4 code lines = 40%
        lines = ["text"] * 4 + ["```"] + ["code"] * 4 + ["```"]
        assert should_speak("\n".join(lines)) is True

    def test_just_over_threshold(self):
        # 5 code lines out of 10 = 50% > 40%
        lines = ["text"] * 3 + ["```"] + ["code"] * 5 + ["```"]
        assert should_speak("\n".join(lines)) is False

    def test_trivial_done(self):
        assert should_speak("Done.") is False

    def test_trivial_got_it(self):
        assert should_speak("Got it.") is False

    def test_trivial_file_created(self):
        assert should_speak("File created.") is False

    def test_trivial_command_completed(self):
        assert should_speak("Command completed.") is False

    def test_trivial_running(self):
        assert should_speak("Running the tests now.") is False

    def test_short_question_speaks(self):
        assert should_speak("Should I continue with the refactor?") is True

    def test_substantive_short_response(self):
        assert should_speak("The auth token expired. You need to refresh it.") is True

    def test_changes_committed(self):
        assert should_speak("Changes committed.") is False


# ---------------------------------------------------------------------------
# classify_tone
# ---------------------------------------------------------------------------

class TestClassifyTone:
    def test_question(self):
        assert classify_tone("Should I refactor this function?") == "question"

    def test_error(self):
        assert classify_tone("Error: the build failed with 3 type errors.") == "error"

    def test_failed(self):
        assert classify_tone("Failed to connect to the database.") == "error"

    def test_warning(self):
        assert classify_tone("Warning: this API is deprecated.") == "warning"

    def test_completion(self):
        assert classify_tone("All tests passed. The feature is complete.") == "completion"

    def test_done(self):
        assert classify_tone("Done. All changes have been applied and verified.") == "completion"

    def test_normal_text(self):
        assert classify_tone("Here is how the auth middleware works.") is None

    def test_empty(self):
        assert classify_tone("") is None
        assert classify_tone(None) is None


# ---------------------------------------------------------------------------
# voice_for_tone
# ---------------------------------------------------------------------------

class TestVoiceForTone:
    def test_error_voice(self):
        voice, speed = voice_for_tone("error")
        assert voice == "am_adam"
        assert speed == 0.9

    def test_question_voice(self):
        voice, speed = voice_for_tone("question")
        assert voice == "af_bella"
        assert speed == 1.05

    def test_completion_voice(self):
        voice, speed = voice_for_tone("completion")
        assert voice == "af_heart"

    def test_unknown_tone(self):
        voice, speed = voice_for_tone("unknown")
        assert voice is None
        assert speed is None

    def test_none_tone(self):
        voice, speed = voice_for_tone(None)
        assert voice is None


# ---------------------------------------------------------------------------
# split_sentences
# ---------------------------------------------------------------------------

class TestSplitSentences:
    def test_short_text_single_chunk(self):
        chunks = split_sentences("Hello world.")
        assert len(chunks) == 1
        assert chunks[0] == "Hello world."

    def test_splits_on_sentence_boundary(self):
        text = "First sentence. Second sentence. Third sentence."
        chunks = split_sentences(text, max_len=40)
        assert len(chunks) >= 2
        assert all(len(c) <= 40 for c in chunks)

    def test_respects_max_len(self):
        text = "A. " * 200  # many short sentences
        chunks = split_sentences(text, max_len=100)
        assert all(len(c) <= 100 for c in chunks)

    def test_long_single_sentence(self):
        text = "This is a very long sentence that exceeds the max length without any sentence boundaries"
        chunks = split_sentences(text, max_len=50)
        # Single sentence exceeds limit but can't be split further
        assert len(chunks) == 1

    def test_empty_input(self):
        assert split_sentences("") == []


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------

class TestSummarize:
    def test_short_text_unchanged(self):
        result = summarize("Short text here.")
        assert "Short text here" in result

    def test_limits_to_three_sentences(self):
        text = "One. Two. Three. Four. Five."
        result = summarize(text)
        assert "Four" not in result
        assert "Five" not in result

    def test_caps_length(self):
        long_sentence = "Word " * 200 + "."
        text = f"{long_sentence} Second. Third."
        result = summarize(text)
        assert len(result) <= 800

    def test_empty_input(self):
        assert summarize("") == ""

    def test_code_only_input(self):
        text = "```python\nprint('hello')\n```"
        assert summarize(text) == ""

    def test_preprocesses_before_summarizing(self):
        text = "The API uses JWT tokens. The CLI sends JSON. Third sentence."
        result = summarize(text)
        assert "A P I" in result
        assert "J W T" in result
