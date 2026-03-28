#!/usr/bin/env python3
"""MCP server for Claude Code TTS — exposes speak/stop tools via the MCP protocol.

Proxies to the Kokoro HTTP daemon at localhost:7723. Lets Claude call TTS
directly as a tool instead of relying only on hooks and CLAUDE.md instructions.

Usage in ~/.claude/settings.json:
  "mcpServers": {
    "tts": {
      "command": "/path/to/venv/bin/python3",
      "args": ["/path/to/mcp-server.py"]
    }
  }
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

KOKORO_URL = f"http://127.0.0.1:{os.environ.get('KOKORO_PORT', '7723')}"


# ---------------------------------------------------------------------------
# MCP protocol helpers (minimal JSON-RPC over stdio, no external deps)
# ---------------------------------------------------------------------------

def _read_message():
    """Read a JSON-RPC message from stdin."""
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line.strip())


def _write_message(msg):
    """Write a JSON-RPC message to stdout."""
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _response(id, result):
    _write_message({"jsonrpc": "2.0", "id": id, "result": result})


def _error(id, code, message):
    _write_message({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}})


# ---------------------------------------------------------------------------
# TTS operations (proxy to HTTP daemon)
# ---------------------------------------------------------------------------

def _daemon_healthy():
    try:
        req = urllib.request.Request(f"{KOKORO_URL}/health", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            return data.get("model_loaded", False)
    except Exception:
        return False


def _speak(text, voice=None, speed=None, mode=None):
    """Send text to the Kokoro daemon for speech synthesis and playback."""
    if not _daemon_healthy():
        return {"success": False, "error": "Kokoro daemon not running"}

    payload = {"text": text}
    if voice:
        payload["voice"] = voice
    if speed:
        payload["speed"] = speed
    if mode:
        payload["mode"] = mode

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{KOKORO_URL}/speak",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        # Kill any existing playback first
        subprocess.run(["pkill", "-f", "ffplay.*claude-tts"], capture_output=True)

        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status == 204:
                tone = resp.headers.get("X-TTS-Tone")
                return {"success": True, "spoken": False, "reason": "skipped (trivial)", "tone": tone}

            # Pipe audio to ffplay
            audio = resp.read()
            proc = subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
                 "-f", "wav", "-window_title", "claude-tts", "-i", "pipe:0"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc.stdin.write(audio)
            proc.stdin.close()
            # Don't wait — return immediately so Claude can continue
            return {"success": True, "spoken": True}

    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _stop():
    """Stop any currently playing TTS audio."""
    result = subprocess.run(["pkill", "-f", "ffplay.*claude-tts"], capture_output=True)
    return {"success": True, "stopped": result.returncode == 0}


def _status():
    """Check TTS daemon status."""
    healthy = _daemon_healthy()
    return {"daemon_running": healthy, "url": KOKORO_URL}


# ---------------------------------------------------------------------------
# MCP protocol handlers
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "speak",
        "description": (
            "Speak text aloud using local TTS. Use when the user says "
            "'read that to me', 'say that', 'speak', or similar. "
            "Also useful for status updates during long tasks."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to speak. Can include markdown — it will be cleaned automatically.",
                },
                "voice": {
                    "type": "string",
                    "description": "Voice ID (default: af_heart). Options: af_heart, af_bella, am_michael, am_adam.",
                },
                "speed": {
                    "type": "number",
                    "description": "Speech speed multiplier (default: 1.0).",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "stop",
        "description": "Stop any currently playing TTS audio immediately.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "status",
        "description": "Check if the TTS daemon is running and ready.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def handle_request(msg):
    method = msg.get("method")
    id = msg.get("id")
    params = msg.get("params", {})

    if method == "initialize":
        _response(id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "claude-code-tts", "version": "0.2.0"},
        })
    elif method == "initialized":
        pass  # notification, no response
    elif method == "tools/list":
        _response(id, {"tools": TOOLS})
    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "speak":
            result = _speak(args.get("text", ""), args.get("voice"), args.get("speed"))
        elif tool_name == "stop":
            result = _stop()
        elif tool_name == "status":
            result = _status()
        else:
            return _error(id, -32601, f"Unknown tool: {tool_name}")

        _response(id, {
            "content": [{"type": "text", "text": json.dumps(result)}],
        })
    elif method == "ping":
        _response(id, {})
    else:
        if id is not None:
            _error(id, -32601, f"Method not found: {method}")


def main():
    while True:
        msg = _read_message()
        if msg is None:
            break
        handle_request(msg)


if __name__ == "__main__":
    main()
