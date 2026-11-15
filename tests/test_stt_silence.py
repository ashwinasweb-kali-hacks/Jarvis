"""Tests for the STT silence / hallucination guards."""
import io
import math
import struct
import wave

import numpy as np

from jarvis import stt


def _wav(samples, rate=16000):
    data = b"".join(struct.pack("<h", max(-32768, min(32767, int(s * 32767)))) for s in samples)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(data)
    return buf.getvalue()


def test_analyze_wav_level_detects_silence():
    level = stt.analyze_wav_level(_wav([0.0] * 80000))
    assert level["silent"] is True
    assert level["rms"] == 0.0
    assert level["duration_ms"] == 5000


def test_analyze_wav_level_detects_speech():
    tone = [0.2 * math.sin(i / 12) for i in range(80000)]
    level = stt.analyze_wav_level(_wav(tone))
    assert level["silent"] is False
    assert level["rms"] > 0.1
    assert level["speech_ratio"] > 0.9


def test_silence_is_rejected_without_calling_a_model(monkeypatch):
    called = []
    monkeypatch.setattr(stt, "transcribe_groq", lambda *a, **k: called.append("groq") or "")
    monkeypatch.setattr(stt, "_local_transcribe_bytes", lambda *a, **k: called.append("local") or "")

    detail = stt.transcribe_wav_bytes_ex(_wav([0.0] * 80000))

    assert detail["ok"] is True
    assert detail["text"] == ""
    assert detail["reason"] == "silence"
    assert detail["engine"] is None
    assert called == []


def test_quiet_audio_does_not_return_hallucinations(monkeypatch):
    monkeypatch.setattr(stt, "transcribe_groq", lambda *a, **k: "Thank you.")
    monkeypatch.setattr(stt, "_local_transcribe_bytes", lambda *a, **k: "Thank you.")

    quiet = [0.01 * math.sin(i / 12) for i in range(80000)]
    detail = stt.transcribe_wav_bytes_ex(_wav(quiet))

    assert detail["text"] == ""
    assert detail["reason"] == "hallucination-filtered"


def test_real_speech_is_transcribed(monkeypatch):
    monkeypatch.setattr(stt, "transcribe_groq", lambda *a, **k: "The engine is online.")

    loud = [0.2 * math.sin(i / 12) for i in range(80000)]
    detail = stt.transcribe_wav_bytes_ex(_wav(loud))

    assert detail["ok"] is True
    assert detail["text"] == "The engine is online."
    assert detail["reason"] is None
    assert detail["engine"] == "groq"


def test_broken_audio_reports_an_error():
    detail = stt.transcribe_wav_bytes_ex(b"not a wav file at all")
    assert detail["ok"] is False
    assert detail["reason"] == "error"
