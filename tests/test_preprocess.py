"""Tests for the TTS preprocessing pipeline."""

import os
import re
import sys

# Add server/ to path so we can import preprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from preprocess import classify_tone, opening_paragraph, preprocess, should_speak, split_sentences, summarize, voice_for_agent, voice_for_tone


# ---------------------------------------------------------------------------
# preprocess: acronym expansion
# ---------------------------------------------------------------------------

class TestAcronyms:
    def test_api(self):
        assert "eh P I" in preprocess("The API is down")

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

    def test_inline_identifier_is_spoken_split(self):
        text = "The `fetchUser` function returns a promise."
        result = preprocess(text)
        assert "fetch User function" in result

    def test_inline_command_is_spoken(self):
        assert "glab M R view 252" in preprocess("Run `glab mr view 252` first")

    def test_inline_snake_case_flag_is_spoken(self):
        result = preprocess("The only codebase with `auto_approval_enabled` was flipped off")
        assert "with auto approval enabled was" in result

    def test_inline_path_keeps_filename_only(self):
        result = preprocess("Edit `~/.claude/hooks/tts-speak.sh:12` next")
        assert "tts-speak dot sh" in result
        assert "claude" not in result

    def test_inline_code_with_braces_is_dropped(self):
        assert preprocess("Pass `{a: 1}` here") == "Pass here"

    def test_inline_code_longer_than_limit_is_dropped(self):
        long_code = "x" * 41
        assert preprocess(f"Use `{long_code}` here") == "Use here"

    def test_inline_flag_loses_leading_dashes(self):
        assert "dry-run" in preprocess("Add `--dry-run` to it")

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
# voice_for_agent
# ---------------------------------------------------------------------------

class TestVoiceForAgent:
    def test_architect(self):
        voice, speed = voice_for_agent("architect")
        assert voice == "af_bella"
        assert speed == 0.95

    def test_planner(self):
        voice, speed = voice_for_agent("planner")
        assert voice == "am_michael"

    def test_contrarian(self):
        voice, speed = voice_for_agent("contrarian")
        assert voice == "am_adam"

    def test_case_insensitive(self):
        voice, _ = voice_for_agent("Architect")
        assert voice == "af_bella"

    def test_unknown_agent(self):
        voice, speed = voice_for_agent("unknown_agent")
        assert voice is None
        assert speed is None

    def test_none(self):
        voice, speed = voice_for_agent(None)
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
        assert "eh P I" in result
        assert "J W T" in result


# ---------------------------------------------------------------------------
# preprocess: links vs URLs ordering
# ---------------------------------------------------------------------------

class TestLinksBeforeUrls:
    def test_link_text_kept_when_followed_by_bare_url(self):
        result = preprocess("See [SFT-910](https://x.y/z) and https://x.y/w")
        assert result == "See S F T 9 10 and U R L"

    def test_image_alt_text_kept(self):
        assert preprocess("Shot: ![the diff](https://x.y/a.png) done") == "Shot: the diff done"

    def test_autolink_angle_brackets(self):
        assert preprocess("See <https://a.b/c> now") == "See U R L now"

    def test_html_tags_stripped(self):
        assert preprocess("<details><summary>Notes here</summary></details>") == "Notes here"


# ---------------------------------------------------------------------------
# preprocess: paths
# ---------------------------------------------------------------------------

class TestPaths:
    def test_dotfile_directory_keeps_name_without_dot(self):
        assert preprocess("Config lives in ~/.claude today") == "Config lives in claude today"

    def test_line_number_suffix_dropped(self):
        assert preprocess("Look at /src/app/main.ts:40:2 please") == "Look at main dot ts please"

    def test_relative_path_with_two_slashes(self):
        assert "Auth dot tsx" in preprocess("Open src/components/Auth.tsx")

    def test_slash_between_words_is_not_a_path(self):
        result = preprocess("Pick MR/PR and/or both")
        assert "M R/P R" in result
        assert "and/or" in result


# ---------------------------------------------------------------------------
# preprocess: tickets, merge requests, issues, channels
# ---------------------------------------------------------------------------

class TestWorkRefs:
    def test_ticket_id_spelled_with_paired_digits(self):
        assert preprocess("Ship SFT-1141 next") == "Ship S F T 11 41 next"

    def test_three_digit_ticket_reads_as_nine_ten(self):
        assert preprocess("SFT-910") == "S F T 9 10"

    def test_round_hundred_ticket_number_left_whole(self):
        assert preprocess("AD-100") == "eh D 100"

    def test_bang_number_is_a_merge_request(self):
        assert preprocess("Merge !249 today") == "Merge M R 2 49 today"

    def test_mr_prefix_plus_bang_not_doubled(self):
        assert preprocess("proofui MR !92") == "proofui M R 92"

    def test_hash_number_is_an_issue_number(self):
        assert preprocess("Closes #12") == "Closes number 12"

    def test_slack_channel_read_as_words(self):
        result = preprocess("Posted in #wg-software-factory-change")
        assert result == "Posted in the wg software factory change channel"

    def test_c_sharp_untouched(self):
        assert "C#" in preprocess("Some C# code")

    def test_lowercase_mr_is_not_mister(self):
        assert preprocess("the mr is open") == "the M R is open"


# ---------------------------------------------------------------------------
# preprocess: dates and times
# ---------------------------------------------------------------------------

class TestDatesAndTimes:
    def test_iso_date_this_year_has_no_year(self):
        import datetime
        year = datetime.date.today().year
        assert preprocess(f"On {year}-09-16 we shipped") == "On September 16th we shipped"

    def test_iso_date_other_year_keeps_year(self):
        assert preprocess("Since 2019-12-01") == "Since December 1st 2019"

    def test_us_slash_date(self):
        assert preprocess("As of 9/15 it is off") == "As of September 15th it is off"

    def test_us_slash_date_with_two_digit_year(self):
        import datetime
        year = datetime.date.today().year
        assert preprocess(f"on 9/15/{year % 100}") == "on September 15th"

    def test_invalid_slash_date_left_alone(self):
        assert "13/45" in preprocess("ratio 13/45")

    def test_ordinal_suffixes(self):
        assert preprocess("1/1 1/2 1/3 1/11 1/21") == "January 1st January 2nd January 3rd January 11th January 21st"

    def test_clock_time_with_pm(self):
        assert preprocess("at 9:44pm ET") == "at 9 44 P M E T"

    def test_clock_time_on_the_hour_drops_minutes(self):
        assert preprocess("at 10:00am") == "at 10 eh M"

    def test_bare_hour_with_meridiem(self):
        assert preprocess("meet at 4pm") == "meet at 4 P M"

    def test_one_on_one_meeting(self):
        assert preprocess("1:1 with Kyle") == "one on one with Kyle"

    def test_one_on_ones_plural_not_a_unit(self):
        assert preprocess("weekly 1:1s") == "weekly one on ones"

    def test_time_without_meridiem(self):
        assert preprocess("ran 1:30 long") == "ran 1 30 long"


# ---------------------------------------------------------------------------
# preprocess: numbers, units, abbreviations, dashes
# ---------------------------------------------------------------------------

class TestNumbersAndSymbols:
    def test_hours_unit_plural(self):
        assert preprocess("took 2hrs") == "took 2 hours"

    def test_approximate_tilde(self):
        assert preprocess("~2hrs left") == "about 2 hours left"

    def test_minutes_plural(self):
        assert preprocess("3 mins") == "3 minutes"

    def test_decimal_point_spoken(self):
        assert preprocess("Python 3.13") == "Python 3 point 13"

    def test_version_prefix_still_uses_dot(self):
        assert preprocess("v2.1.3") == "version 2 dot 1 dot 3"

    def test_eg_expanded(self):
        assert preprocess("e.g. the MR") == "for example the M R"

    def test_ie_expanded(self):
        assert preprocess("i.e. MRs") == "that is M R s"

    def test_vs_expanded(self):
        assert preprocess("this vs. that") == "this versus that"

    def test_em_dash_becomes_comma(self):
        assert preprocess("Kyle \u2014 and Lauren") == "Kyle, and Lauren"

    def test_spaced_hyphen_becomes_comma(self):
        assert preprocess("fast - and safe") == "fast, and safe"

    def test_ampersand(self):
        assert preprocess("R&D team") == "R and D team"

    def test_emoji_shortcode_removed(self):
        assert preprocess(":tada: shipped it") == "shipped it"

    def test_colon_separated_numbers_are_not_a_shortcode(self):
        assert preprocess("main.ts:40:2 please") == "main dot ts please"

    def test_no_space_before_punctuation(self):
        assert preprocess("Use `{x}` , then stop .") == "Use, then stop."


# ---------------------------------------------------------------------------
# preprocess: unknown acronyms
# ---------------------------------------------------------------------------

class TestAcronymDefault:
    def test_unknown_all_caps_is_spelled(self):
        assert preprocess("EOD wrap") == "E O D wrap"

    def test_unknown_acronym_plural(self):
        assert preprocess("Q4 OKRs") == "Q4 O K R s"

    def test_dictionary_word_in_caps_stays_a_word(self):
        assert preprocess("NOT this one, the NEXT step") == "NOT this one, the NEXT step"

    def test_plural_dictionary_word_stays_a_word(self):
        assert preprocess("SCARS") == "SCARS"

    def test_allowlisted_acronym_stays_a_word(self):
        assert preprocess("WIP branch") == "WIP branch"

    def test_dictionary_words_that_are_really_acronyms_are_mapped(self):
        assert preprocess("ETA for the US") == "E T eh for the U S"

    def test_alphanumeric_code_spelled(self):
        assert preprocess("IC4 level") == "I C 4 level"

    def test_alphanumeric_word_kept(self):
        assert preprocess("ARM64 chips") == "ARM64 chips"

    def test_letter_a_uses_letter_sound(self):
        assert preprocess("API") == "eh P I"

    def test_no_mapped_value_ends_in_bare_letter_a(self):
        """A trailing " A" is read as the article "uh" by espeak; use "eh"."""
        import preprocess as P
        offenders = [k for k, v in P.PRONUNCIATION.items() if re.search(r"\bA\b", v)]
        assert offenders == []

    def test_six_letter_caps_word_untouched(self):
        assert preprocess("IMPORTANT") == "IMPORTANT"

    def test_split_identifier_exposes_mapped_term(self):
        assert preprocess("parseJSON") == "parse jason"


# ---------------------------------------------------------------------------
# config: local overlay merging and json/builtin parity
# ---------------------------------------------------------------------------

class TestConfig:
    def test_overlay_dict_merges_per_key(self):
        from preprocess import merge_config
        merged = merge_config({"pronunciation": {"A": "a", "B": "b"}}, {"pronunciation": {"B": "bee", "C": "c"}})
        assert merged["pronunciation"] == {"A": "a", "B": "bee", "C": "c"}

    def test_overlay_list_appends_without_duplicates(self):
        from preprocess import merge_config
        merged = merge_config({"acronym_words": ["WIP"]}, {"acronym_words": ["WIP", "SCARS"]})
        assert merged["acronym_words"] == ["WIP", "SCARS"]

    def test_overlay_scalar_replaces(self):
        from preprocess import merge_config
        assert merge_config({"x": 1}, {"x": 2}) == {"x": 2}

    def test_bundled_word_list_is_used(self):
        """CI runners have no /usr/share/dict/words; the bundled list must carry the rule."""
        import preprocess as P
        assert P._DICTIONARY_PATHS[0].endswith("words-2to5.txt")
        assert os.path.isfile(P._DICTIONARY_PATHS[0])
        words = P._dictionary()
        assert {"not", "next", "scar"} <= words
        assert not {"eod", "okr", "et"} & words

    def test_shipped_json_matches_builtins(self):
        """pronunciation.json replaces the built-ins wholesale, so the two must not drift."""
        import json
        import preprocess as P
        with open(os.path.join(os.path.dirname(P.__file__), "pronunciation.json")) as f:
            shipped = json.load(f)
        assert shipped["pronunciation"] == P._BUILTIN_PRONUNCIATION
        assert shipped["units"] == P._BUILTIN_UNITS
        assert [tuple(s) for s in shipped["symbols"]] == P._BUILTIN_SYMBOLS
        assert shipped["abbreviations"] == P._BUILTIN_ABBREVIATIONS
        assert shipped["acronym_words"] == P._BUILTIN_ACRONYM_WORDS


class TestSummarizeGate:
    def test_bare_url_message_is_not_spoken(self):
        assert summarize("https://gitlab.com/zapier/proofapi/-/merge_requests/252") == ""

    def test_short_real_sentence_still_spoken(self):
        assert summarize("Short text here.") == "Short text here."


# ---------------------------------------------------------------------------
# summarize: stops at the opening paragraph
# ---------------------------------------------------------------------------

class TestOpeningParagraph:
    def test_stops_at_blank_line(self):
        text = "The fix landed. Tests pass.\n\n**Coverage:** sources 6 OK\n- item"
        assert opening_paragraph(text) == "The fix landed. Tests pass."

    def test_stops_before_list_without_blank_line(self):
        text = "Two things changed.\n- first\n- second"
        assert opening_paragraph(text) == "Two things changed."

    def test_colon_line_ends_the_block(self):
        text = "Here's where both stand:\n- Memory, done.\n- Coverage: 6 OK"
        assert opening_paragraph(text) == "Here's where both stand:"

    def test_skips_leading_heading_and_code(self):
        text = "## Summary\n\n```bash\nls\n```\nThat lists files.\n\nMore below."
        assert opening_paragraph(text) == "That lists files."

    def test_empty_when_response_is_only_a_list(self):
        assert opening_paragraph("- one\n- two") == ""


class TestSummarizeOpeningParagraph:
    def test_does_not_read_into_list_below(self):
        text = "Yes, the PR is merged. The daemon restarted cleanly.\n\nCoverage: sources 6 OK / 0 FAILED\n- item one"
        assert summarize(text) == "Yes, the P R is merged. The daemon restarted cleanly."

    def test_list_intro_loses_trailing_colon(self):
        text = "Here's where both stand:\n- Memory, done.\n- Coverage: sources 6 OK"
        assert summarize(text) == "Here's where both stand."

    def test_falls_back_to_whole_text_when_no_opening_prose(self):
        text = "- First item that is long enough to speak.\n- Second item here."
        assert summarize(text) == "First item that is long enough to speak. Second item here."

    def test_still_limited_to_three_sentences_within_paragraph(self):
        assert summarize("One is here. Two is here. Three is here. Four is here.") == "One is here. Two is here. Three is here."


class TestNoiseTokens:
    def test_commit_hash_dropped(self):
        assert preprocess("PR 19 squash-merged as de2beaa today.") == "P R 19 squash-merged as today."

    def test_plain_words_and_numbers_kept(self):
        assert preprocess("deadbeef 1234567 accede") == "deadbeef 1234567 accede"

    def test_empty_parens_removed(self):
        assert preprocess("merged via (`gh pr merge 19 --squash --delete-branch --admin`) cleanly") == "merged via cleanly"
