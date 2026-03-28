"""Text preprocessing for TTS — makes developer content sound natural when spoken."""

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

# ---------------------------------------------------------------------------
# Pronunciation / units / symbols — loaded from pronunciation.json if present,
# otherwise fall back to built-in defaults.
# ---------------------------------------------------------------------------

_script_dir = os.path.dirname(os.path.abspath(__file__))
_json_path = os.path.join(_script_dir, "pronunciation.json")

_BUILTIN_PRONUNCIATION = {
    "API": "A P I",
    "APIs": "A P I s",
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
    "AWS": "A W S",
    "GCP": "G C P",
    "CI": "C I",
    "CD": "C D",
    "PR": "P R",
    "PRs": "P R s",
    "MR": "M R",
    "MRs": "M R s",
    "OAuth": "oh auth",
    "GraphQL": "graph Q L",
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
}

_BUILTIN_UNITS = {
    "ms": "milliseconds",
    "s": "seconds",
    "min": "minutes",
    "hr": "hours",
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
    # Scope resolution (C++/Rust) — collapse to space so "std::vector" becomes "std vector"
    ("::", " "),
    # Ellipsis — just remove it; TTS pauses naturally at sentence boundaries
    ("...", " "),
]


def _load_maps():
    """Load pronunciation maps from JSON file if it exists, else use built-in defaults."""
    if os.path.isfile(_json_path):
        try:
            with open(_json_path, "r") as f:
                data = json.load(f)
            pronunciation = data.get("pronunciation", _BUILTIN_PRONUNCIATION)
            units = data.get("units", _BUILTIN_UNITS)
            # symbols come as [["=>", " arrow "], ...] in JSON — convert to list of tuples
            raw_symbols = data.get("symbols", _BUILTIN_SYMBOLS)
            symbols = [(s[0], s[1]) for s in raw_symbols]
            return pronunciation, units, symbols
        except (json.JSONDecodeError, KeyError, IndexError):
            pass
    return _BUILTIN_PRONUNCIATION, _BUILTIN_UNITS, _BUILTIN_SYMBOLS


PRONUNCIATION, UNITS, SYMBOLS = _load_maps()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def preprocess(text):
    """Clean text for natural-sounding TTS output."""

    # 1. Strip code blocks (fenced ```...```)
    text = re.sub(r'```[\s\S]*?```', '', text)

    # 2. Strip inline code — remove the content, not just backticks.
    #    "the `fetchUser` function" → "the function"
    #    Identifiers inside backticks are usually unpronounceable; dropping them
    #    produces cleaner speech than trying to read "fetch User".
    text = re.sub(r'`[^`]+`', '', text)

    # 3. Replace URLs with "URL" — reading full URLs aloud is never useful
    text = re.sub(r'https?://\S+', 'URL', text)

    # 4. Simplify file paths — keep just the filename.
    #    /src/components/Auth.tsx → Auth.tsx
    text = re.sub(r'(?<!\w)[/~][\w./\-]+/(\w+\.?\w*)', r'\1', text)

    # 5. Clean markdown formatting
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # links → text
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)  # headers
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)  # italic
    text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)  # bullets
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)  # numbered lists
    text = re.sub(r'^\|.*\|$', '', text, flags=re.MULTILINE)  # tables
    text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)  # horizontal rules
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)  # blockquotes

    # 6. Operators and symbols (before other transformations so "=>" doesn't
    #    get partially matched by later regex passes)
    for sym, spoken in SYMBOLS:
        text = text.replace(sym, spoken)

    # 7. File extensions — ".py" → " dot py" so TTS pronounces them
    text = re.sub(r'\.([a-zA-Z]{1,4})\b', lambda m: f' dot {m.group(1)}', text)

    # 8. Version numbers: v2.1.3 → version 2 dot 1 dot 3
    text = re.sub(
        r'\bv(\d+(?:\.\d+)+)\b',
        lambda m: 'version ' + ' dot '.join(m.group(1).split('.')),
        text,
    )

    # 9. Numbers with units: 15ms → 15 milliseconds
    unit_pattern = '|'.join(re.escape(u) for u in sorted(UNITS.keys(), key=len, reverse=True))
    text = re.sub(
        rf'\b(\d+)\s*({unit_pattern})\b',
        lambda m: f'{m.group(1)} {UNITS[m.group(2)]}',
        text,
    )

    # 10. Split camelCase: fetchUserData → fetch User Data
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

    # 11. Split snake_case: user_name → user name
    text = re.sub(r'(\w)_(\w)', r'\1 \2', text)

    # 12. Pronunciation map (word boundaries, case-sensitive)
    for term, spoken in PRONUNCIATION.items():
        text = re.sub(rf'\b{re.escape(term)}\b', spoken, text)

    # 13. Strip emoji — TTS models produce silence or artifacts for emoji codepoints
    text = re.sub(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
        r'\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF'
        r'\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF]',
        '', text,
    )

    # 14. Normalize whitespace
    text = re.sub(r'\n{2,}', '. ', text)  # paragraph breaks → sentence boundary
    text = re.sub(r'\n', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
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


def summarize(text):
    """Produce a short spoken summary: preprocess, take first few sentences, cap length.

    Useful for auto-speak hooks that need a quick synopsis rather than
    reading an entire response aloud.
    """
    cleaned = preprocess(text)
    if not cleaned:
        return ""

    # Split into sentences, take first N
    sentences = re.split(r'(?<=[.!?])\s+', cleaned)
    summary = " ".join(sentences[:SUMMARY_MAX_SENTENCES])

    # Cap total length
    if len(summary) > SUMMARY_MAX_CHARS:
        summary = summary[:SUMMARY_MAX_CHARS].rsplit(" ", 1)[0]

    return summary
