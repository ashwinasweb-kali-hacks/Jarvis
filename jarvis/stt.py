"""Local speech-to-text using faster-whisper.

The size comes from ``jarvis.voice_models``: by default the best free local
model (``small.en``), overridable with ``JARVIS_STT_MODEL`` or the raw
``JARVIS_MODEL`` size. Includes hallucination/noise filtering, high
``no_speech_prob`` suppression and low ``avg_logprob`` filtering (Stage 2.4).
"""
from typing import Any, Dict, Optional, Set, Tuple, Union
from pathlib import Path
import io
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave

import numpy as np

from jarvis import voice_models

_models: Dict[Tuple[str, str, str], object] = {}

# Known hallucination phrases emitted by Whisper on background noise / silence
DEFAULT_HALLUCINATION_BLOCKLIST: Set[str] = {
    "thank you.",
    "thank you",
    "you",
    "you.",
    "thanks for watching.",
    "thanks for watching!",
    "subtitles by",
    "subtitle by",
    "subscribe",
    "watching",
    "bye.",
    "bye",
    ".",
    "...",
}

# Audio level gates. Whisper happily invents "Thank you." on silence, so a
# recording that carries no real signal is rejected before any model runs.
SILENCE_RMS_THRESHOLD = 0.0035   # ~ -49 dBFS: nothing but room noise
QUIET_RMS_THRESHOLD = 0.02       # ~ -34 dBFS: too quiet to trust a short phrase
SPEECH_FRAME_RMS = 0.01          # per 20 ms frame, counts as "something was said"


def resolve_model_size(model_size: Optional[str] = None) -> str:
    """Whisper size for a given model id/size (default: best free model)."""
    return voice_models.whisper_size(model_size)


def get_model(
    model_size: Optional[str] = None,
    device: str = "cpu",
    compute_type: str = "int8",
):
    """Lazy-load and cache the WhisperModel instance."""
    return preload_model(model_size=model_size, device=device, compute_type=compute_type)


WHISPER_CACHE_DIR = Path(os.environ.get("JARVIS_WHISPER_DIR", r"E:\JARVIS\models\whisper"))

def preload_model(
    model_size: Optional[str] = None,
    device: str = "cpu",
    compute_type: str = "int8",
):
    """Preload and warm up the Whisper model, printing status messages."""
    size = resolve_model_size(model_size)
    key = (size, device, compute_type)
    if key not in _models:
        from faster_whisper import WhisperModel

        print(f"Loading speech model ({size})...", flush=True)
        WHISPER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _models[key] = WhisperModel(
            size,
            device=device,
            compute_type=compute_type,
            download_root=str(WHISPER_CACHE_DIR),
        )
        print("Model ready.", flush=True)
    return _models[key]


def filter_text(
    text: str,
    no_speech_prob: float = 0.0,
    avg_logprob: float = 0.0,
    max_no_speech_prob: float = 0.6,
    min_avg_logprob: float = -1.5,
    blocklist: Optional[Set[str]] = None,
) -> str:
    """Filter candidate transcript against hallucination blocklists and confidence bounds.

    Returns sanitized transcript string or empty string if filtered.
    """
    cleaned = text.strip()
    if not cleaned:
        return ""

    # Confidence check
    if no_speech_prob > max_no_speech_prob:
        return ""
    if avg_logprob < min_avg_logprob:
        return ""

    # Hallucination blocklist check
    bl = blocklist if blocklist is not None else DEFAULT_HALLUCINATION_BLOCKLIST
    if cleaned.lower() in bl:
        return ""

    return cleaned


def transcribe(
    audio: Union[str, np.ndarray],
    language: str = "en",
    condition_on_previous_text: bool = False,
    max_no_speech_prob: float = 0.6,
    min_avg_logprob: float = -1.5,
    model_size: Optional[str] = None,
) -> str:
    """Transcribe audio (file path or 16 kHz float32 numpy array) to filtered text.

    Args:
        audio: Path to audio file or 1D float32 numpy array.
        language: Language code ("en" forced as per spec).
        condition_on_previous_text: False to prevent loop hallucinations.
        max_no_speech_prob: Maximum allowed no_speech_prob threshold.
        min_avg_logprob: Minimum allowed avg_logprob threshold.
        model_size: Whisper size or STT model id (default: best free model).
    """
    model = get_model(model_size=model_size)
    segments, _ = model.transcribe(
        audio,
        language=language,
        condition_on_previous_text=condition_on_previous_text,
        vad_filter=True,
    )

    valid_parts = []
    for seg in segments:
        part = filter_text(
            seg.text,
            no_speech_prob=getattr(seg, "no_speech_prob", 0.0),
            avg_logprob=getattr(seg, "avg_logprob", 0.0),
            max_no_speech_prob=max_no_speech_prob,
            min_avg_logprob=min_avg_logprob,
        )
        if part:
            valid_parts.append(part)

    return " ".join(valid_parts).strip()


def wav_bytes_to_float32(data: bytes, target_rate: int = 16000) -> np.ndarray:
    """Decode mono 16-bit PCM WAV bytes (what the browser sends) to float32."""
    with wave.open(io.BytesIO(data), "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    if width != 2:
        raise ValueError(f"expected 16-bit PCM, got {width * 8}-bit")

    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != target_rate and len(samples):
        # Cheap linear resample: the browser sends 16 kHz already, this is a guard.
        count = int(round(len(samples) * target_rate / rate))
        samples = np.interp(
            np.linspace(0.0, len(samples) - 1, count, dtype=np.float32),
            np.arange(len(samples), dtype=np.float32),
            samples,
        ).astype(np.float32)
    return samples


def transcribe_wav_bytes(
    data: bytes,
    language: str = "en",
    model_size: Optional[str] = None,
) -> str:
    """Transcribe recorded WAV bytes locally (no cloud, no API key)."""
    audio = wav_bytes_to_float32(data)
    return transcribe(audio, language=language, model_size=model_size)


def analyze_wav_level(data: bytes) -> Dict[str, Any]:
    """Measure a WAV recording: level, peak and how much of it looks like speech.

    Used to stop Whisper from hallucinating on silence ("Thank you." on an empty
    microphone is the classic symptom of a broken mic or a muted input).
    """
    try:
        samples = wav_bytes_to_float32(data)
    except Exception as exc:
        return {"error": str(exc), "silent": False, "rms": 0.0, "peak": 0.0}

    if samples.size == 0:
        return {
            "duration_ms": 0,
            "rms": 0.0,
            "peak": 0.0,
            "speech_ratio": 0.0,
            "level_db": -120.0,
            "silent": True,
        }

    values = samples.astype(np.float64)
    rms = float(np.sqrt(np.mean(np.square(values))))
    peak = float(np.max(np.abs(values)))

    frame = max(1, int(0.02 * 16000))
    usable = (len(values) // frame) * frame
    if usable:
        frames = values[:usable].reshape(-1, frame)
        frame_rms = np.sqrt(np.mean(np.square(frames), axis=1))
        speech_ratio = float(np.mean(frame_rms > SPEECH_FRAME_RMS))
    else:
        speech_ratio = 0.0

    return {
        "duration_ms": int(len(values) / 16.0),
        "rms": round(rms, 6),
        "peak": round(peak, 6),
        "speech_ratio": round(speech_ratio, 4),
        "level_db": round(20.0 * math.log10(rms) if rms > 0 else -120.0, 1),
        "silent": rms < SILENCE_RMS_THRESHOLD,
    }


# ----------------------------------------------------------------- Groq cloud
GROQ_TRANSCRIPTIONS_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_DEFAULT_MODEL = "whisper-large-v3-turbo"
GROQ_TIMEOUT_SECONDS = 4.0

# The cached WhisperModel is not thread-safe, so local calls are serialised.
_LOCAL_LOCK = threading.Lock()


def groq_key() -> Optional[str]:
    """Groq API key from the vault (env ``GROQ_API_KEY`` wins), if any."""
    try:
        from jarvis import keyvault

        value = keyvault.get_key("groq")
    except Exception:
        value = os.environ.get("GROQ_API_KEY")
    return value.strip() if value else None


def _groq_multipart(data: bytes, model: str, language: str) -> Tuple[bytes, str]:
    boundary = "----jarvis" + uuid.uuid4().hex
    fields = [
        ("model", model),
        ("response_format", "json"),
        ("language", language),
        ("temperature", "0"),
    ]
    body = bytearray()
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
    body += b"Content-Type: audio/wav\r\n\r\n"
    body += data + b"\r\n"
    for name, value in fields:
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        body += str(value).encode() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def transcribe_groq(
    data: bytes,
    model: str = GROQ_DEFAULT_MODEL,
    language: str = "en",
    timeout: float = GROQ_TIMEOUT_SECONDS,
) -> str:
    """Transcribe WAV bytes with Groq's hosted Whisper (low latency)."""
    key = groq_key()
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set (env or key vault)")

    body, content_type = _groq_multipart(data, model, language)
    request = urllib.request.Request(
        GROQ_TRANSCRIPTIONS_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": content_type,
            "User-Agent": "jarvis-daemon/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Groq HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Groq unreachable: {exc.reason}") from exc

    return str(payload.get("text", "")).strip()


def _local_transcribe_bytes(data: bytes, language: str, model_size: Optional[str]) -> str:
    with _LOCAL_LOCK:
        audio = wav_bytes_to_float32(data)
        return transcribe(audio, language=language, model_size=model_size)


def transcribe_wav_bytes_ex(
    data: bytes,
    language: str = "en",
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Transcribe WAV bytes with the selected engine, then the other one.

    Selection comes from ``JARVIS_STT_MODEL`` / the catalog (Groq by default).
    If the primary fails - no key, offline, rate limit - the fallback runs so
    voice input keeps working instead of returning an empty transcript.

    Two guards run before any model is called:

    * a recording that is effectively silent is rejected outright, because
      Whisper invents phrases such as "Thank you." on empty audio;
    * a transcript that matches the hallucination blocklist is dropped when the
      recording was too quiet to contain a real sentence.
    """
    selected = (model_id or voice_models.stt_model()).strip()
    try:
        entry = voice_models.get_stt(selected)
    except ValueError:
        entry = {"id": selected, "engine": "faster_whisper", "model": selected}

    local_size = voice_models.whisper_size(None)
    groq_model = GROQ_DEFAULT_MODEL
    if entry.get("engine") == "groq":
        groq_model = str(entry.get("model") or groq_model)

    try:
        from jarvis import aimode
        local_mode = (aimode.mode() == "local")
    except Exception:
        local_mode = False

    if local_mode:
        primary = "local"
        order = ("local", "groq")
    else:
        primary = "groq" if entry.get("engine") == "groq" else "local"
        order = ("groq", "local") if primary == "groq" else ("local", "groq")
    errors = []
    started = time.time()

    level = analyze_wav_level(data)
    if level.get("error"):
        return {
            "ok": False,
            "text": "",
            "engine": None,
            "model": None,
            "fallback": False,
            "elapsed_ms": int((time.time() - started) * 1000),
            "error": "unreadable audio: {0}".format(level["error"]),
            "reason": "error",
            "level": level,
            "errors": errors,
        }

    if level.get("silent"):
        return {
            "ok": True,
            "text": "",
            "engine": None,
            "model": None,
            "fallback": False,
            "elapsed_ms": int((time.time() - started) * 1000),
            "error": None,
            "reason": "silence",
            "message": "No speech in the recording (level {0} dBFS). Nothing was sent to the model.".format(
                level.get("level_db")
            ),
            "level": level,
            "errors": errors,
        }

    for engine in order:
        try:
            if engine == "groq":
                if not groq_key():
                    raise RuntimeError("GROQ_API_KEY is not set (env or key vault)")
                text = transcribe_groq(data, model=groq_model, language=language)
                label, used_model = "groq", groq_model
            else:
                text = _local_transcribe_bytes(data, language=language, model_size=local_size)
                label, used_model = "faster-whisper", local_size

            cleaned = (text or "").strip()
            too_quiet = level.get("rms", 1.0) < QUIET_RMS_THRESHOLD
            no_speech_frames = level.get("speech_ratio", 1.0) < 0.05
            if cleaned.lower() in DEFAULT_HALLUCINATION_BLOCKLIST and (too_quiet or no_speech_frames):
                return {
                    "ok": True,
                    "text": "",
                    "engine": label,
                    "model": used_model,
                    "fallback": primary != ("groq" if engine == "groq" else "local"),
                    "elapsed_ms": int((time.time() - started) * 1000),
                    "error": None,
                    "reason": "hallucination-filtered",
                    "message": "Discarded a likely hallucination ('{0}') - the recording was too quiet.".format(cleaned),
                    "level": level,
                    "errors": errors,
                }

            return {
                "ok": True,
                "text": cleaned,
                "engine": label,
                "model": used_model,
                "fallback": primary != ("groq" if engine == "groq" else "local"),
                "elapsed_ms": int((time.time() - started) * 1000),
                "error": None,
                "reason": None,
                "level": level,
                "errors": errors,
            }
        except Exception as exc:
            errors.append(f"{engine}: {exc}")

    return {
        "ok": False,
        "text": "",
        "engine": None,
        "model": None,
        "fallback": False,
        "elapsed_ms": int((time.time() - started) * 1000),
        "error": "; ".join(errors) or "speech recognition failed",
        "reason": "error",
        "level": level,
        "errors": errors,
    }