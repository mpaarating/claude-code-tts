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

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
PORT = int(os.environ.get("KOKORO_PORT", 7723))
VOICE = os.environ.get("KOKORO_VOICE", "af_heart")
SPEED = float(os.environ.get("KOKORO_SPEED", "1.0"))

kokoro = None


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
