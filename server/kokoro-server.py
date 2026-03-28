#!/usr/bin/env python3
"""Kokoro TTS HTTP daemon — keeps model loaded, serves audio on demand."""

import io
import json
import os
import signal
import sys
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import numpy as np
import soundfile as sf

# Import from sibling module. Works whether run from the repo (server/ dir)
# or from an installed location (~/.local/share/kokoro-tts/) because both
# layouts put preprocess.py next to kokoro-server.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preprocess import (
    preprocess,
    split_sentences,
    summarize,
    MAX_CHUNK_LEN,
    INTER_CHUNK_SILENCE_SECS,
)

# Models dir: check sibling "models/" first (installed layout), then "../models/" (repo layout)
_script_dir = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(_script_dir, "models")
if not os.path.isdir(MODEL_DIR):
    MODEL_DIR = os.path.join(_script_dir, "..", "models")
PORT = int(os.environ.get("KOKORO_PORT", 7723))
VOICE = os.environ.get("KOKORO_VOICE", "af_heart")
SPEED = float(os.environ.get("KOKORO_SPEED", "1.0"))

tts_model = None


def load_model():
    global tts_model
    from kokoro_onnx import Kokoro
    tts_model = Kokoro(
        os.path.join(MODEL_DIR, "kokoro-v1.0.onnx"),
        os.path.join(MODEL_DIR, "voices-v1.0.bin"),
    )
    print(f"Kokoro model loaded. Listening on :{PORT}", flush=True)


class TTSHandler(BaseHTTPRequestHandler):
    # Intentionally suppress per-request access logging — the daemon runs
    # locally and logs just add noise to launchd/systemd output.
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/health":
            body = {"status": "ok", "model_loaded": tts_model is not None}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())
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

    def _send_error(self, code, error_message=""):
        self.send_response(code)
        if error_message:
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": error_message}).encode())
        else:
            self.end_headers()

    def do_POST(self):
        if self.path in ("/speak", "/speak-long"):
            self._handle_speak()
        else:
            self._send_error(404)

    def _handle_speak(self):
        """Smart speak handler — short text gets a single generation,
        long text is chunked on sentence boundaries and concatenated.
        Supports optional "mode": "summary" to summarize before generating."""
        data, text = self._parse_body()
        if not text:
            return self._send_error(400)

        voice = data.get("voice", VOICE)
        speed = data.get("speed", SPEED)
        mode = data.get("mode")

        # Apply summary mode if requested
        if mode == "summary":
            text = summarize(text)
        else:
            text = preprocess(text)

        if not text:
            return self._send_error(400, "Nothing speakable after preprocessing")

        try:
            if len(text) > MAX_CHUNK_LEN:
                self._generate_chunked(text, voice, speed)
            else:
                samples, sample_rate = tts_model.create(text, voice=voice, speed=speed)
                self._send_wav(samples, sample_rate)
        except Exception as e:
            self._send_error(500, str(e))

    def _generate_chunked(self, text, voice, speed):
        """Chunk text on sentence boundaries, generate each, concatenate into one WAV."""
        chunks = split_sentences(text)
        all_samples = []
        sample_rate = None

        for chunk in chunks:
            if not chunk.strip():
                continue
            samples, sample_rate = tts_model.create(chunk.strip(), voice=voice, speed=speed)
            all_samples.append(samples)
            # Brief silence between chunks for natural pacing
            silence = np.zeros(int(sample_rate * INTER_CHUNK_SILENCE_SECS), dtype=samples.dtype)
            all_samples.append(silence)

        if not all_samples or sample_rate is None:
            return self._send_error(400, "No speakable text")

        combined = np.concatenate(all_samples)
        self._send_wav(combined, sample_rate)


def main():
    load_model()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), TTSHandler)

    def shutdown(sig, frame):
        print("\nShutting down.", flush=True)
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    server.serve_forever()


if __name__ == "__main__":
    main()
