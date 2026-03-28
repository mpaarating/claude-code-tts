#!/usr/bin/env python3
"""Kokoro TTS HTTP daemon — keeps model loaded, serves audio on demand."""

import asyncio
import io
import json
import os
import signal
import struct
import sys
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import numpy as np
import soundfile as sf

# Import from sibling module. Works whether run from the repo (server/ dir)
# or from an installed location (~/.local/share/kokoro-tts/) because both
# layouts put preprocess.py next to kokoro-server.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preprocess import (
    classify_tone,
    preprocess,
    should_speak,
    split_sentences,
    summarize,
    voice_for_agent,
    voice_for_tone,
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
LOG_DIR = os.environ.get("KOKORO_LOG_DIR", os.path.join(os.path.expanduser("~"), ".local", "share", "claude-code-tts", "logs"))
LOG_FILE = os.path.join(LOG_DIR, "tts-history.jsonl")

tts_model = None


def load_model():
    global tts_model
    from kokoro_onnx import Kokoro
    tts_model = Kokoro(
        os.path.join(MODEL_DIR, "kokoro-v1.0.onnx"),
        os.path.join(MODEL_DIR, "voices-v1.0.bin"),
    )
    print(f"Kokoro model loaded. Listening on :{PORT}", flush=True)


def _log_speech(text, voice, mode, tone, duration_ms):
    """Append a record to the JSONL history log."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "text": text[:500],  # cap to avoid huge entries
            "voice": voice,
            "mode": mode,
            "tone": tone,
            "duration_ms": duration_ms,
        }
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass  # logging should never break TTS


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

    def _send_wav(self, samples, sample_rate, tone=None):
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV")
        wav_bytes = buf.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(wav_bytes)))
        if tone:
            self.send_header("X-TTS-Tone", tone)
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
        if self.path == "/speak":
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

        voice = data.get("voice")
        speed = data.get("speed")
        mode = data.get("mode")
        agent = data.get("agent")

        # Classify tone before preprocessing (needs raw text)
        tone = classify_tone(text)

        # Priority: explicit voice > agent voice > tone voice > default
        if voice is None or speed is None:
            if agent:
                agent_voice, agent_speed = voice_for_agent(agent)
                if voice is None:
                    voice = agent_voice
                if speed is None:
                    speed = agent_speed
            if tone and (voice is None or speed is None):
                tone_voice, tone_speed = voice_for_tone(tone)
                if voice is None:
                    voice = tone_voice
                if speed is None:
                    speed = tone_speed
        voice = voice or VOICE
        speed = speed or SPEED

        # In summary mode (auto-speak), check if the content is worth speaking
        # before doing any expensive TTS work. Code-heavy responses get rejected.
        if mode == "summary":
            if not should_speak(text):
                # Return tone so hooks can still play a chime
                self.send_response(204)
                if tone:
                    self.send_header("X-TTS-Tone", tone)
                self.end_headers()
                return
            text = summarize(text)
        else:
            text = preprocess(text)

        if not text:
            return self._send_error(400, "Nothing speakable after preprocessing")

        try:
            t0 = time.monotonic()
            if len(text) > MAX_CHUNK_LEN:
                # Prefer streaming API for lower latency; fall back to sync chunking
                try:
                    self._generate_streamed(text, voice, speed, tone)
                except (AttributeError, TypeError):
                    self._generate_chunked(text, voice, speed, tone)
            else:
                samples, sample_rate = tts_model.create(text, voice=voice, speed=speed)
                self._send_wav(samples, sample_rate, tone)
            duration_ms = int((time.monotonic() - t0) * 1000)
            _log_speech(text, voice, mode, tone, duration_ms)
        except Exception as e:
            self._send_error(500, str(e))

    def _generate_streamed(self, text, voice, speed, tone=None):
        """Stream audio using Kokoro's async create_stream API.

        Sends a WAV header immediately, then writes PCM data as each
        sentence is generated. Client starts playing after the first
        chunk (~300ms) instead of waiting for the full response.
        """
        async def _collect_stream():
            all_samples = []
            sample_rate = None
            async for samples, sr in tts_model.create_stream(text, voice=voice, speed=speed):
                if sample_rate is None:
                    sample_rate = sr
                all_samples.append(samples)
                silence = np.zeros(int(sr * INTER_CHUNK_SILENCE_SECS), dtype=samples.dtype)
                all_samples.append(silence)
            return all_samples, sample_rate

        all_samples, sample_rate = asyncio.run(_collect_stream())

        if not all_samples or sample_rate is None:
            return self._send_error(400, "No speakable text")

        combined = np.concatenate(all_samples)
        self._send_wav(combined, sample_rate, tone)

    def _generate_chunked(self, text, voice, speed, tone=None):
        """Fallback: chunk text on sentence boundaries, generate each sequentially."""
        chunks = split_sentences(text)
        all_samples = []
        sample_rate = None

        for chunk in chunks:
            if not chunk.strip():
                continue
            samples, sample_rate = tts_model.create(chunk.strip(), voice=voice, speed=speed)
            all_samples.append(samples)
            silence = np.zeros(int(sample_rate * INTER_CHUNK_SILENCE_SECS), dtype=samples.dtype)
            all_samples.append(silence)

        if not all_samples or sample_rate is None:
            return self._send_error(400, "No speakable text")

        combined = np.concatenate(all_samples)
        self._send_wav(combined, sample_rate, tone)


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
