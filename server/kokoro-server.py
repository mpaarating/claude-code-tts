#!/usr/bin/env python3
"""Kokoro TTS HTTP daemon — keeps model loaded, serves audio on demand."""

import json
import os
import re
import signal
import struct
import sys
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import numpy as np

# Import from sibling module. Works whether run from the repo (server/ dir)
# or from an installed location (~/.local/share/kokoro-tts/) because both
# layouts put preprocess.py next to kokoro-server.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preprocess import (
    classify_tone,
    preprocess,
    should_speak,
    summarize,
    voice_for_agent,
    voice_for_tone,
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

# Audio is streamed one sentence at a time so playback starts after the first
# sentence is synthesized instead of after the whole response. Sentences
# shorter than this are merged into the next one: "Done." is not worth its
# own model pass.
MIN_STREAM_CHUNK_CHARS = 40
_SENTENCE_END = re.compile(r'(?<=[.!?])\s+')

tts_model = None


def load_model():
    global tts_model
    from kokoro_onnx import Kokoro
    tts_model = Kokoro(
        os.path.join(MODEL_DIR, "kokoro-v1.0.onnx"),
        os.path.join(MODEL_DIR, "voices-v1.0.bin"),
    )
    print(f"Kokoro model loaded. Listening on :{PORT}", flush=True)


def _log_speech(text, voice, mode, tone, duration_ms, first_audio_ms=None, interrupted=False):
    """Append a record to the JSONL history log.

    duration_ms is total synthesis time; first_audio_ms is how long the
    client waited before the first sentence started playing."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "text": text[:500],  # cap to avoid huge entries
            "voice": voice,
            "mode": mode,
            "tone": tone,
            "duration_ms": duration_ms,
            "first_audio_ms": first_audio_ms,
            "interrupted": interrupted,
        }
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass  # logging should never break TTS


def stream_chunks(text, min_chars=MIN_STREAM_CHUNK_CHARS):
    """Split text into sentence-sized synthesis chunks for streaming.

    Sentences shorter than min_chars are merged forward so tiny fragments
    don't each cost a model pass, but the first chunk is kept as small as
    possible because its synthesis time is the time to first audio."""
    sentences = [s for s in _SENTENCE_END.split(text) if s.strip()]
    chunks = []
    current = ""
    for sentence in sentences:
        if current and len(current) < min_chars:
            current = f"{current} {sentence}"
        elif current:
            chunks.append(current)
            current = sentence
        else:
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def wav_header(sample_rate, channels=1, bits=16):
    """RIFF/WAVE header for a PCM stream of unknown length.

    0xFFFFFFFF in the size fields tells players (ffplay, ffmpeg) to read until
    EOF, so the body can be written sentence by sentence as it is synthesized."""
    block_align = channels * bits // 8
    return (
        b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, sample_rate,
                                sample_rate * block_align, block_align, bits)
        + b"data" + struct.pack("<I", 0xFFFFFFFF)
    )


def pcm16(samples):
    """float32 [-1, 1] samples -> little-endian 16-bit PCM bytes."""
    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    return (clipped * 32767).astype("<i2").tobytes()


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
        elif self.path == "/preprocess":
            self._handle_preprocess()
        else:
            self._send_error(404)

    def _handle_preprocess(self):
        """Return the text exactly as it would be handed to the model, without
        generating audio. Backs `tts-speak.sh --dry-run` so a bad pronunciation
        can be traced to either preprocessing or the model itself."""
        data, text = self._parse_body()
        if not text:
            return self._send_error(400)
        mode = data.get("mode")
        spoken = summarize(text) if mode == "summary" else preprocess(text)
        body = {
            "text": spoken,
            "mode": mode or "full",
            "tone": classify_tone(text),
            "would_speak": bool(spoken) and (mode != "summary" or should_speak(text)),
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

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
            if not text:
                # e.g. a bare link that preprocesses to just "U R L"
                self.send_response(204)
                self.end_headers()
                return
        else:
            text = preprocess(text)

        if not text:
            return self._send_error(400, "Nothing speakable after preprocessing")

        try:
            self._stream_speech(text, voice, speed, mode, tone)
        except Exception as e:
            self._send_error(500, str(e))

    def _stream_speech(self, text, voice, speed, mode, tone=None):
        """Synthesize sentence by sentence and write each as PCM as soon as it
        is ready. The client (curl piped into ffplay) starts playing after the
        first sentence instead of after the whole response.

        If the client goes away mid-stream (playback interrupted), synthesis
        stops at the next sentence instead of burning CPU on unheard audio."""
        chunks = stream_chunks(text)
        t0 = time.monotonic()
        first_audio_ms = None
        interrupted = False
        try:
            for i, chunk in enumerate(chunks):
                samples, sample_rate = tts_model.create(chunk.strip(), voice=voice, speed=speed)
                if i == 0:
                    first_audio_ms = int((time.monotonic() - t0) * 1000)
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/wav")
                    self.send_header("Connection", "close")
                    if tone:
                        self.send_header("X-TTS-Tone", tone)
                    self.end_headers()
                    self.wfile.write(wav_header(sample_rate))
                else:
                    self.wfile.write(bytes(int(sample_rate * INTER_CHUNK_SILENCE_SECS) * 2))
                self.wfile.write(pcm16(samples))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            interrupted = True
        except Exception:
            # Headers already sent for a later chunk: nothing useful can be
            # returned to the client, so end the stream where it is.
            if first_audio_ms is None:
                raise
            interrupted = True
        duration_ms = int((time.monotonic() - t0) * 1000)
        _log_speech(text, voice, mode, tone, duration_ms, first_audio_ms, interrupted)


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
