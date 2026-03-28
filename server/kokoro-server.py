#!/usr/bin/env python3
"""Kokoro TTS HTTP daemon — keeps model loaded, serves audio on demand."""

import io
import json
import os
import re
import signal
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

import numpy as np
import soundfile as sf

# Models dir: check sibling "models/" first (installed layout), then "../models/" (repo layout)
_script_dir = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(_script_dir, "models")
if not os.path.isdir(MODEL_DIR):
    MODEL_DIR = os.path.join(_script_dir, "..", "models")
PORT = int(os.environ.get("KOKORO_PORT", 7723))
VOICE = os.environ.get("KOKORO_VOICE", "af_heart")
SPEED = float(os.environ.get("KOKORO_SPEED", "1.0"))

kokoro = None

# ---------------------------------------------------------------------------
# Text preprocessing — make developer content sound natural when spoken
# ---------------------------------------------------------------------------

# Acronyms and dev terms → spoken form (applied with word boundaries)
PRONUNCIATION = {
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
    "args": "args",
    "config": "config",
    "configs": "configs",
    "vite": "veet",
}

# Units → expanded form
UNITS = {
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

# Operators and symbols → spoken form
SYMBOLS = [
    ("=>", " arrow "),
    ("->", " arrow "),
    ("!==", " not equal to "),
    ("!=", " not equal to "),
    ("===", " equals "),
    ("==", " equals "),
    (">=", " greater than or equal to "),
    ("<=", " less than or equal to "),
    ("&&", " and "),
    ("||", " or "),
    ("::", " "),
    ("...", " "),
]


def preprocess(text):
    """Clean text for natural-sounding TTS output."""

    # 1. Strip code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)

    # 2. Strip inline code — remove the content, not just backticks
    #    "the `fetchUser` function" → "the function"
    text = re.sub(r'`[^`]+`', '', text)

    # 3. Replace URLs with "URL"
    text = re.sub(r'https?://\S+', 'URL', text)

    # 4. Simplify file paths — keep just the filename
    #    /src/components/Auth.tsx → Auth.tsx
    text = re.sub(r'(?<!\w)[/~][\w./\-]+/(\w+\.?\w*)', r'\1', text)

    # 5. Clean markdown
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # links → text
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)  # headers
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)  # italic
    text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)  # bullets
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)  # numbered lists
    text = re.sub(r'^\|.*\|$', '', text, flags=re.MULTILINE)  # tables
    text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)  # horizontal rules
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)  # blockquotes

    # 6. Operators and symbols (before other transformations)
    for sym, spoken in SYMBOLS:
        text = text.replace(sym, spoken)

    # 7. File extensions
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

    # 13. Strip emoji
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


def _split_sentences(text, max_len=500):
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


def load_model():
    global kokoro
    from kokoro_onnx import Kokoro
    kokoro = Kokoro(
        os.path.join(MODEL_DIR, "kokoro-v1.0.onnx"),
        os.path.join(MODEL_DIR, "voices-v1.0.bin"),
    )
    print(f"Kokoro model loaded. Listening on :{PORT}", flush=True)


class TTSHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def _parse_body(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
            text = data.get("text", "").strip()
        except (json.JSONDecodeError, AttributeError):
            return None, None
        return data, text

    def _send_wav(self, samples, sample_rate):
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV")
        wav_bytes = buf.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(wav_bytes)))
        self.end_headers()
        self.wfile.write(wav_bytes)

    def _send_error(self, code, msg=""):
        self.send_response(code)
        if msg:
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": msg}).encode())
        else:
            self.end_headers()

    def do_POST(self):
        if self.path == "/speak":
            self._handle_speak()
        elif self.path == "/speak-long":
            self._handle_speak_long()
        else:
            self._send_error(404)

    def _handle_speak(self):
        """Short text — generate and return a single WAV."""
        data, text = self._parse_body()
        if not text:
            return self._send_error(400)

        voice = data.get("voice", VOICE)
        speed = data.get("speed", SPEED)
        text = preprocess(text)
        if not text:
            return self._send_error(400, "Nothing speakable after preprocessing")

        try:
            samples, sample_rate = kokoro.create(text, voice=voice, speed=speed)
            self._send_wav(samples, sample_rate)
        except Exception as e:
            self._send_error(500, str(e))

    def _handle_speak_long(self):
        """Long text — chunk, generate each, concatenate into one seamless WAV."""
        data, text = self._parse_body()
        if not text:
            return self._send_error(400)

        voice = data.get("voice", VOICE)
        speed = data.get("speed", SPEED)
        text = preprocess(text)
        if not text:
            return self._send_error(400, "Nothing speakable after preprocessing")

        chunks = _split_sentences(text)

        try:
            all_samples = []
            sample_rate = None
            for chunk in chunks:
                if not chunk.strip():
                    continue
                samples, sr = kokoro.create(chunk.strip(), voice=voice, speed=speed)
                sample_rate = sr
                all_samples.append(samples)
                all_samples.append(np.zeros(int(sr * 0.15), dtype=samples.dtype))

            if not all_samples or sample_rate is None:
                return self._send_error(400, "No speakable text")

            combined = np.concatenate(all_samples)
            self._send_wav(combined, sample_rate)
        except Exception as e:
            self._send_error(500, str(e))


def main():
    load_model()
    server = HTTPServer(("127.0.0.1", PORT), TTSHandler)

    def shutdown(sig, frame):
        print("\nShutting down.", flush=True)
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    server.serve_forever()


if __name__ == "__main__":
    main()
