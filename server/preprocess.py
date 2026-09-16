"""Text preprocessing for TTS — makes developer content sound natural when spoken."""

import datetime
import json
import os
import re

# ---------------------------------------------------------------------------
# Named constants
# ---------------------------------------------------------------------------

MAX_CHUNK_LEN = 500
INTER_CHUNK_SILENCE_SECS = 0.15
SUMMARY_MAX_SENTENCES = 3
SUMMARY_MAX_CHARS = 800
MIN_SPEAKABLE_LEN = 20
CODE_RATIO_THRESHOLD = 40  # percent — skip if response is mostly code
# Short responses under this length must contain a question to be spoken —
# trivial acknowledgments ("Done.", "Got it.") aren't worth hearing.
SUBSTANCE_THRESHOLD = 80
# A summary needs this many real words (3+ letters) after preprocessing, or
# it's noise: a bare link becomes just "U R L".
MIN_SUMMARY_WORDS = 2

# Inline code is spoken when it's a short identifier or command ("fetchUser",
# "glab mr view 252"). Anything longer, or containing path/operator characters,
# is identifier soup and gets dropped instead.
MAX_SPOKEN_INLINE_CODE = 40
_UNSPEAKABLE_INLINE_CODE = re.compile(r'[\\{}<>|$=;`()\[\]]')

# All-caps tokens in this length range that aren't dictionary words get spelled
# out letter by letter ("EOD" -> "E O D"). espeak otherwise guesses a word
# ("owd") and guesses differently depending on the surrounding text.
ACRONYM_MIN_LEN = 2
ACRONYM_MAX_LEN = 5
_DICTIONARY_PATHS = ("/usr/share/dict/words", "/usr/dict/words")

_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

# Trivial patterns that add noise in auto-speak mode.
# Checked against the full raw text (before preprocessing).
_TRIVIAL_PATTERNS = [
    r"^(done|got it|ok|okay|sure|yes|no|noted|understood|will do)\.?$",
    r"^(file|directory|branch) (created|deleted|updated|renamed|moved)\.?$",
    r"^command completed\.?$",
    r"^changes? (saved|committed|staged|applied)\.?$",
    r"^(running|starting|checking|reading|writing)\b",
]

# ---------------------------------------------------------------------------
# Configuration — built-in defaults, overridden per key by pronunciation.json,
# then merged with pronunciation.local.json (machine-specific terms that
# shouldn't live in the shared file: team names, internal services).
# ---------------------------------------------------------------------------

_script_dir = os.path.dirname(os.path.abspath(__file__))
_json_path = os.path.join(_script_dir, "pronunciation.json")
_local_json_path = os.path.join(_script_dir, "pronunciation.local.json")

_BUILTIN_PRONUNCIATION = {
    "API": "eh P I",
    "APIs": "eh P I s",
    "CLI": "C L I",
    "CPU": "C P U",
    "GPU": "G P U",
    "GUI": "gooey",
    "IDE": "I D E",
    "IO": "I O",
    "IP": "I P",
    "JSON": "jason",
    "JWT": "J W T",
    "LLM": "L L M",
    "MCP": "M C P",
    "NPM": "N P M",
    "npm": "N P M",
    "OS": "O S",
    "REST": "rest",
    "SDK": "S D K",
    "SQL": "sequel",
    "SQLite": "sequel light",
    "SSH": "S S H",
    "SSL": "S S L",
    "STT": "S T T",
    "TLS": "T L S",
    "TTS": "T T S",
    "UI": "you eye",
    "URL": "U R L",
    "URLs": "U R L s",
    "UX": "you ex",
    "UUID": "you you I D",
    "YAML": "yaml",
    "XML": "X M L",
    "HTML": "H T M L",
    "CSS": "C S S",
    "DNS": "D N S",
    "HTTP": "H T T P",
    "HTTPS": "H T T P S",
    "AWS": "eh W S",
    "GCP": "G C P",
    "CI": "C I",
    "CD": "C D",
    "PR": "P R",
    "PRs": "P R s",
    "MR": "M R",
    "MRs": "M R s",
    # Lowercase forms show up in commands quoted in prose ("run glab mr view").
    # Without these espeak reads "mr" as "mister".
    "mr": "M R",
    "mrs": "M R s",
    # Dictionary words that are almost always acronyms in engineering prose.
    "US": "U S",
    "AM": "eh M",
    "ETA": "E T eh",
    "OAuth": "oh auth",
    "GraphQL": "graph Q L",
    "PostgreSQL": "postgres sequel",
    "Redis": "red iss",
    "SaaS": "sass",
    "iOS": "I O S",
    "macOS": "mac O S",
    "k8s": "kubernetes",
    "a11y": "accessibility",
    "i18n": "internationalization",
    "async": "a-sink",
    "stdout": "standard out",
    "stderr": "standard error",
    "stdin": "standard in",
    "sudo": "sue-doo",
    "nginx": "engine x",
    "kubectl": "kube control",
    "wget": "w-get",
    "regex": "reg ex",
    "enum": "ee num",
    "kwargs": "keyword args",
    "vite": "veet",
    "venv": "V env",
    "npx": "N P X",
    "tmux": "T mux",
    "ffplay": "F F play",
}

_BUILTIN_UNITS = {
    "ms": "milliseconds",
    "s": "seconds",
    "sec": "seconds",
    "secs": "seconds",
    "min": "minutes",
    "mins": "minutes",
    "hr": "hours",
    "hrs": "hours",
    "KB": "kilobytes",
    "MB": "megabytes",
    "GB": "gigabytes",
    "TB": "terabytes",
    "kB": "kilobytes",
    "GHz": "gigahertz",
    "MHz": "megahertz",
    "Mbps": "megabits per second",
    "Gbps": "gigabits per second",
    "req": "requests",
    "ops": "operations",
    "rpm": "requests per minute",
    "rps": "requests per second",
    "QPS": "queries per second",
}

_BUILTIN_SYMBOLS = [
    ("=>", " arrow "),
    ("->", " arrow "),
    # Order matters: triple-char operators before double-char to avoid partial matches
    ("!==", " not equal to "),
    ("!=", " not equal to "),
    ("===", " equals "),
    ("==", " equals "),
    (">=", " greater than or equal to "),
    ("<=", " less than or equal to "),
    ("&&", " and "),
    ("||", " or "),
    ("&", " and "),
    # Em/en dashes are clause breaks; a comma gives the same pause reliably.
    ("—", ", "),
    ("–", ", "),
    # Scope resolution (C++/Rust) — collapse to space so "std::vector" becomes "std vector"
    ("::", " "),
    # Ellipsis — just remove it; TTS pauses naturally at sentence boundaries
    ("…", " "),
    ("...", " "),
]

# Latin abbreviations, expanded before the file-extension rule would turn
# "e.g." into "e dot g". Matched case-insensitively on word boundaries.
_BUILTIN_ABBREVIATIONS = {
    "e.g.": "for example",
    "i.e.": "that is",
    "etc.": "et cetera",
    "vs.": "versus",
    "approx.": "approximately",
    "w/o": "without",
    "w/": "with",
}

# All-caps tokens that are pronounced as words even though they aren't in the
# system dictionary. Everything else all-caps and unknown gets spelled out.
_BUILTIN_ACRONYM_WORDS = [
    "WIP", "NASA", "GIF", "SAML", "CRUD", "ACID", "OWASP", "RAG", "SOC",
    "YOLO", "FOMO", "LGBT", "GUI", "JSON", "YAML", "REST", "SCRUM",
]

# Tone → voice/speed mapping. Used when no explicit voice is provided.
_BUILTIN_TONE_VOICES = {
    "error":      {"voice": "am_adam",    "speed": 0.9},
    "question":   {"voice": "af_bella",   "speed": 1.05},
    "completion":  {"voice": "af_heart",  "speed": 1.0},
    "warning":    {"voice": "am_adam",    "speed": 0.95},
}

# Agent type → voice mapping.
_BUILTIN_AGENT_VOICES = {
    "planner":    {"voice": "am_michael", "speed": 1.0},
    "orchestrator": {"voice": "am_michael", "speed": 1.0},
    "reviewer":   {"voice": "af_bella",   "speed": 1.0},
    "architect":  {"voice": "af_bella",   "speed": 0.95},
    "nitpicker":  {"voice": "af_bella",   "speed": 1.05},
    "researcher": {"voice": "af_heart",   "speed": 1.0},
    "contrarian": {"voice": "am_adam",    "speed": 0.95},
}

_BUILTIN_CONFIG = {
    "pronunciation": _BUILTIN_PRONUNCIATION,
    "units": _BUILTIN_UNITS,
    "symbols": _BUILTIN_SYMBOLS,
    "abbreviations": _BUILTIN_ABBREVIATIONS,
    "acronym_words": _BUILTIN_ACRONYM_WORDS,
    "tone_voices": _BUILTIN_TONE_VOICES,
    "agent_voices": _BUILTIN_AGENT_VOICES,
}


def _read_json(path):
    """Return the JSON object at path, or {} when missing or malformed."""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def merge_config(base, overlay):
    """Merge overlay into base: dicts merge per key, lists append, scalars replace.

    Used for pronunciation.local.json so a machine-specific file only has to
    list its additions, not repeat the whole shared table.
    """
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            merged[key] = {**current, **value}
        elif isinstance(value, list) and isinstance(current, list):
            merged[key] = current + [item for item in value if item not in current]
        else:
            merged[key] = value
    return merged


def _load_config():
    # pronunciation.json replaces a built-in section wholesale (it's the shared
    # source of truth); pronunciation.local.json merges on top.
    config = {**_BUILTIN_CONFIG, **_read_json(_json_path)}
    return merge_config(config, _read_json(_local_json_path))


CONFIG = _load_config()
PRONUNCIATION = CONFIG["pronunciation"]
UNITS = CONFIG["units"]
SYMBOLS = [(s[0], s[1]) for s in CONFIG["symbols"]]
ABBREVIATIONS = CONFIG["abbreviations"]
ACRONYM_WORDS = set(CONFIG["acronym_words"])
TONE_VOICES = CONFIG["tone_voices"]
AGENT_VOICES = CONFIG["agent_voices"]

_dictionary_words = None


def _dictionary():
    """Lowercase system word list, loaded once. Empty set when unavailable."""
    global _dictionary_words
    if _dictionary_words is None:
        _dictionary_words = set()
        for path in _DICTIONARY_PATHS:
            if os.path.isfile(path):
                with open(path, "r", errors="ignore") as f:
                    _dictionary_words = {line.strip().lower() for line in f if line.strip()}
                break
    return _dictionary_words


def _is_word(token):
    """True when an all-caps token should be pronounced as a word, not spelled."""
    if token in ACRONYM_WORDS:
        return True
    words = _dictionary()
    if not words:
        # No dictionary on this machine: fall back to "has a vowel, treat as word".
        return bool(re.search(r"[AEIOUY]", token))
    lower = token.lower()
    # web2 has no plurals, so "SCARS" checks "scar".
    return lower in words or (lower.endswith("s") and lower[:-1] in words)


# espeak reads a standalone "A" as the article ("uh"); "eh" gives the letter.
_LETTER_SOUNDS = {"A": "eh"}


def _spell(letters):
    return " ".join(_LETTER_SOUNDS.get(ch, ch) for ch in letters)


# ---------------------------------------------------------------------------
# Replacement helpers
# ---------------------------------------------------------------------------


def _say_id_number(digits):
    """Read an identifier number the way people say ticket numbers.

    1141 -> "11 41" (eleven forty-one), 910 -> "9 10" (nine ten). Round
    hundreds and anything over four digits are left for espeak to read as a
    plain number.
    """
    if len(digits) == 3 and digits[1:] != "00":
        return f"{digits[0]} {digits[1:]}"
    if len(digits) == 4 and digits[2:] != "00":
        return f"{digits[:2]} {digits[2:]}"
    return digits


def _ordinal(day):
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _say_date(month, day, year=None):
    """Return 'September 15th' (with year when it isn't this year), or None if invalid."""
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    spoken = f"{_MONTHS[month - 1]} {_ordinal(day)}"
    if year is not None and year != datetime.date.today().year:
        spoken += f" {year}"
    return spoken


def _iso_date(m):
    spoken = _say_date(int(m.group(2)), int(m.group(3)), int(m.group(1)))
    return spoken or m.group(0)


def _us_date(m):
    year = m.group(3)
    if year is not None:
        year = int(year)
        if year < 100:
            year += 2000
    spoken = _say_date(int(m.group(1)), int(m.group(2)), year)
    return spoken or m.group(0)


def _clock_time(m):
    hour, minutes, meridiem = m.group(1), m.group(2), m.group(3)
    spoken = hour if minutes == "00" else f"{hour} {minutes}"
    if meridiem:
        spoken += f" {_spell(meridiem.upper())} M"
    return spoken


def _spoken_inline_code(m):
    code = m.group(1).strip()
    code = _PATH_RE.sub(_simplify_path, code)
    code = code.lstrip("-")  # "--dry-run" -> "dry-run"
    if not code or len(code) > MAX_SPOKEN_INLINE_CODE or _UNSPEAKABLE_INLINE_CODE.search(code):
        return ""
    return code


def _simplify_path(m):
    """Keep only the last path segment, minus line numbers and a leading dot."""
    last = m.group(0).rstrip("/").split("/")[-1]
    last = re.sub(r":\d+(?::\d+)?$", "", last)
    return last.lstrip(".")


def _spell_acronym(m):
    letters, plural = m.group(1), m.group(2) or ""
    if _is_word(letters):
        return m.group(0)
    return f"{_spell(letters)} {plural}".rstrip()


def _spell_alphanumeric(m):
    letters, digits = m.group(1), m.group(2)
    if _is_word(letters):
        return m.group(0)
    return f"{_spell(letters)} {digits}"


def _apply_pronunciation(text):
    for term, spoken in PRONUNCIATION.items():
        text = re.sub(rf"\b{re.escape(term)}\b", spoken, text)
    return text


# Absolute/home/relative-dot paths, or relative paths with at least two
# slashes, optionally suffixed with :line or :line:col. The lookbehind keeps
# "and/or", "MR/PR" and "9/15" from matching.
_PATH_RE = re.compile(
    r"(?<![\w./])(?:(?:~|\.{1,2})?(?:/[\w.\-@~+]+)+|[\w.\-]+(?:/[\w.\-@~+]+){2,})(?::\d+(?::\d+)?)?"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def preprocess(text):
    """Clean text for natural-sounding TTS output."""

    # 1. Strip code blocks (fenced ```...```)
    text = re.sub(r'```[\s\S]*?```', '', text)

    # 2. Inline code: speak short identifiers and commands, drop the rest.
    #    "the `auto_approval_enabled` flag" -> "the auto approval enabled flag"
    text = re.sub(r'`([^`]+)`', _spoken_inline_code, text)

    # 3. Markdown links and images -> their text. Must run before URLs are
    #    replaced, or the URL regex swallows the closing paren.
    text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'<(https?://[^>]+)>', r'\1', text)

    # 4. Replace URLs with "URL" — reading full URLs aloud is never useful
    text = re.sub(r'(?:https?://|www\.)\S+', 'URL', text)

    # 5. Clean markdown / HTML formatting
    text = re.sub(r'<[^>\n]+>', '', text)  # inline HTML tags (<details>, <br>)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)  # headers
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)  # italic
    text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)  # bullets
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)  # numbered lists
    text = re.sub(r'^\|.*\|$', '', text, flags=re.MULTILINE)  # tables
    text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)  # horizontal rules
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)  # blockquotes
    text = re.sub(r'(?<!\w):[a-z][\w+\-]*:', ' ', text)  # emoji shortcodes :tada:

    # 6. Latin abbreviations, before "." handling below would split them
    for abbrev, spoken in sorted(ABBREVIATIONS.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf'(?<!\w){re.escape(abbrev)}(?!\w)', spoken, text, flags=re.IGNORECASE)

    # 7. Operators and symbols
    for sym, spoken in SYMBOLS:
        text = text.replace(sym, spoken)
    text = re.sub(r'\s-\s', ', ', text)  # spaced hyphen used as a dash

    # 8. Dates: 2026-09-16 and 9/15 (or 9/15/26) -> "September 16th"
    text = re.sub(r'\b(\d{4})-(\d{2})-(\d{2})\b', _iso_date, text)
    text = re.sub(r'\b(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?\b(?!/)', _us_date, text)

    # 9. Times. "1:1" is a meeting, not one o'clock.
    text = re.sub(r'\b1:1(s?)\b', r'one on one\1', text)
    text = re.sub(
        r'\b(\d{1,2}):(\d{2})(?::\d{2})?\s*(?:([apAP])\.?[mM]\.?)?(?!\w)',
        _clock_time,
        text,
    )
    text = re.sub(
        r'\b(\d{1,2})\s*([apAP])\.?[mM]\.?(?!\w)',
        lambda m: f'{m.group(1)} {_spell(m.group(2).upper())} M',
        text,
    )

    # 10. File paths -> last segment. Dates ran first so "9/15/26" isn't a path.
    text = _PATH_RE.sub(_simplify_path, text)

    # 11. Tickets, merge requests, issues, channels
    #     SFT-1141 -> "S F T 11 41"; !249 -> "M R 2 49"; #12 -> "number 12";
    #     #wg-software-factory -> "the wg software factory channel"
    text = re.sub(
        r'\b([A-Z]{2,6})-(\d+)\b',
        lambda m: f'{_spell(m.group(1))} {_say_id_number(m.group(2))}',
        text,
    )
    text = re.sub(
        r'(?:\bMR\s+)?(?<!\w)!(\d+)\b',  # "MR !92" and "!92" both -> one "M R 92"
        lambda m: f'M R {_say_id_number(m.group(1))}',
        text,
    )
    text = re.sub(r'(?<!\w)#(\d+)\b', r'number \1', text)
    text = re.sub(
        r'(?<!\w)#([A-Za-z][\w\-]+)',
        lambda m: f"the {m.group(1).replace('-', ' ').replace('_', ' ')} channel",
        text,
    )

    # 12. File extensions — ".py" → " dot py" so TTS pronounces them.
    #     A bare "main.ts:40:2" loses its line:col first.
    text = re.sub(r'(\.[a-zA-Z]{1,4}):\d+(?::\d+)?\b', r'\1', text)
    text = re.sub(r'\.([a-zA-Z]{1,4})\b', lambda m: f' dot {m.group(1)}', text)

    # 13. Version numbers: v2.1.3 → version 2 dot 1 dot 3
    text = re.sub(
        r'\bv(\d+(?:\.\d+)+)\b',
        lambda m: 'version ' + ' dot '.join(m.group(1).split('.')),
        text,
    )

    # 14. Approximation tilde: ~2hrs -> about 2hrs
    text = re.sub(r'[~≈]\s*(?=\d)', 'about ', text)

    # 15. Numbers with units: 15ms → 15 milliseconds
    unit_pattern = '|'.join(re.escape(u) for u in sorted(UNITS.keys(), key=len, reverse=True))
    text = re.sub(
        rf'\b(\d+)\s*({unit_pattern})\b',
        lambda m: f'{m.group(1)} {UNITS[m.group(2)]}',
        text,
    )

    # 16. Decimal points: 3.13 -> "3 point 13" (espeak otherwise pauses at the dot)
    text = re.sub(r'(?<=\d)\.(?=\d)', ' point ', text)

    # 17. Pronunciation map, then split identifiers, then map again so terms
    #     exposed by the split ("parseJSON" -> "parse JSON") are still caught.
    text = _apply_pronunciation(text)
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)  # camelCase
    text = re.sub(r'(\w)_(\w)', r'\1 \2', text)  # snake_case
    text = _apply_pronunciation(text)

    # 18. Unknown acronyms get spelled out; alphanumeric codes too (IC4 -> I C 4)
    text = re.sub(r'\b([A-Z]{2,5})(\d{1,4})\b', _spell_alphanumeric, text)
    text = re.sub(
        rf'\b([A-Z]{{{ACRONYM_MIN_LEN},{ACRONYM_MAX_LEN}}})(s)?\b',
        _spell_acronym,
        text,
    )

    # 19. Strip emoji — TTS models produce silence or artifacts for emoji codepoints
    text = re.sub(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
        r'\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF'
        r'\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF'
        r'\U0000FE0F\U0000200D]',
        '', text,
    )

    # 20. Normalize whitespace
    text = re.sub(r'\n{2,}', '. ', text)  # paragraph breaks → sentence boundary
    text = re.sub(r'\n', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'\s+([,.!?;:])', r'\1', text)  # no space before punctuation
    text = re.sub(r'([,.!?;:])(?:\s*\1)+', r'\1', text)  # collapse ".." / ", ,"
    text = text.strip()

    return text


def split_sentences(text, max_len=MAX_CHUNK_LEN):
    """Split text into chunks on sentence boundaries, each <= max_len chars."""
    sentences = re.split(r'(?<=[.!?])\s+', text)

    chunks = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > max_len:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip() if current else sentence

    if current:
        chunks.append(current)
    return chunks


def should_speak(text):
    """Decide whether raw text (before preprocessing) is worth speaking.

    Returns False for code-heavy or too-short responses where TTS would
    produce garbled output. Centralizes the classification logic so hooks
    don't need to duplicate it.
    """
    if not text or len(text) < MIN_SPEAKABLE_LEN:
        return False

    lines = text.split("\n")
    total = len(lines)
    if total == 0:
        return False

    # Count lines inside fenced code blocks
    inside_code = False
    code_lines = 0
    for line in lines:
        if line.strip().startswith("```"):
            inside_code = not inside_code
            continue
        if inside_code:
            code_lines += 1

    code_ratio = code_lines * 100 // total
    if code_ratio > CODE_RATIO_THRESHOLD:
        return False

    # Short, non-question responses are usually trivial acknowledgments
    stripped = text.strip()
    if len(stripped) < SUBSTANCE_THRESHOLD and "?" not in stripped:
        # Check against trivial patterns
        first_line = stripped.split("\n")[0].strip()
        for pattern in _TRIVIAL_PATTERNS:
            if re.match(pattern, first_line, re.IGNORECASE):
                return False

    return True


def classify_tone(text):
    """Classify response tone for chime selection.

    Returns one of: "error", "question", "completion", "warning", or None (default).
    Uses simple keyword matching on raw text — no ML needed.
    """
    if not text:
        return None

    first_line = text.strip().split("\n")[0].lower()
    full_lower = text.lower()

    if text.rstrip().endswith("?"):
        return "question"

    error_words = ("error", "failed", "failure", "exception", "traceback", "blocked", "broke", "crash")
    if any(w in first_line for w in error_words):
        return "error"

    warning_words = ("warning", "caution", "note:", "careful", "deprecated", "⚠")
    if any(w in first_line for w in warning_words):
        return "warning"

    completion_words = ("done", "complete", "finished", "fixed", "shipped", "merged", "deployed", "passed")
    if any(w in full_lower[:200] for w in completion_words):
        return "completion"

    return None


def voice_for_tone(tone):
    """Return (voice, speed) for a given tone, or (None, None) for default."""
    if tone and tone in TONE_VOICES:
        entry = TONE_VOICES[tone]
        return entry.get("voice"), entry.get("speed")
    return None, None


def voice_for_agent(agent_type):
    """Return (voice, speed) for a given agent type, or (None, None) for default."""
    if not agent_type:
        return None, None
    # Try exact match first, then lowercase
    key = agent_type if agent_type in AGENT_VOICES else agent_type.lower()
    if key in AGENT_VOICES:
        entry = AGENT_VOICES[key]
        return entry.get("voice"), entry.get("speed")
    return None, None


def summarize(text):
    """Produce a short spoken summary: preprocess, take first few sentences, cap length.

    Useful for auto-speak hooks that need a quick synopsis rather than
    reading an entire response aloud. Returns "" when nothing worth hearing
    survives preprocessing (a bare link becomes just "U R L").
    """
    cleaned = preprocess(text)
    if not cleaned or len(re.findall(r"[A-Za-z]{3,}", cleaned)) < MIN_SUMMARY_WORDS:
        return ""

    # Split into sentences, take first N
    sentences = re.split(r'(?<=[.!?])\s+', cleaned)
    summary = " ".join(sentences[:SUMMARY_MAX_SENTENCES])

    # Cap total length
    if len(summary) > SUMMARY_MAX_CHARS:
        summary = summary[:SUMMARY_MAX_CHARS].rsplit(" ", 1)[0]

    return summary
