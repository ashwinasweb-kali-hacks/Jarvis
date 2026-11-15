"""Full offline simulation test for live conversation in LOCAL mode.

The brain stage needs a running Ollama with the local models pulled, so it is
skipped on machines without one instead of failing the suite.
"""
import io
import socket
import time

import numpy as np
import pytest
import soundfile as sf

from jarvis import aimode, brain, ollama_local, stt, tts


def _ollama_ready() -> bool:
    try:
        return bool(ollama_local.list_loaded(timeout=2.0)) or ollama_local.available()
    except Exception:
        return False


skip_without_ollama = pytest.mark.skipif(
    not _ollama_ready(), reason="needs a local Ollama server with the models pulled"
)


@skip_without_ollama
def test_full_offline_conversation_pipeline(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_AI_MODE", "local")
    aimode.set_mode("local")

    # Block all external network traffic
    real_getaddrinfo = socket.getaddrinfo

    def mock_getaddrinfo(host, port, *args, **kwargs):
        if host in ("127.0.0.1", "localhost", "::1"):
            return real_getaddrinfo(host, port, *args, **kwargs)
        raise socket.gaierror(11001, f"Offline: blocked {host}")

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    # 1. Test offline STT
    buf = io.BytesIO()
    samples = (np.sin(2 * np.pi * 300 * np.linspace(0, 1.0, 16000)) * 0.3).astype("float32")
    sf.write(buf, samples, 16000, format="WAV", subtype="PCM_16")
    wav_data = buf.getvalue()

    stt_res = stt.transcribe_wav_bytes_ex(wav_data)
    assert stt_res.get("engine") == "faster-whisper" or stt_res.get("ok") is True

    # 2. Test offline Brain (Local Ollama)
    reply = brain.respond("What is 10 plus 15?")
    assert "local:" in reply.engine or reply.engine == "pc-control"
    assert len(reply.speech) > 0

    # 3. Test offline TTS (pyttsx3)
    tts_res = tts.synthesize(reply.speech, fallback=True)
    assert tts_res.get("ok") is True
    assert tts_res.get("model") == "pyttsx3"
    assert len(tts_res.get("audio", b"")) > 1000
