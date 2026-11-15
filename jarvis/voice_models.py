"""Free text-to-speech (TTS) and speech-to-text (STT) model catalog.

Same idea as ``jarvis/free_models.py``: a short, honest list of engines that
need no account and no paid key, with the trade-offs spelled out. Each
direction marks one ``default`` — the best free option that still runs on a
normal CPU.

Environment overrides:

- ``JARVIS_TTS_MODEL``  TTS engine id from :data:`TTS_CATALOG`
- ``JARVIS_STT_MODEL``  STT engine id from :data:`STT_CATALOG`
- ``JARVIS_MODEL``      raw faster-whisper size (``tiny``, ``base.en``, ...),
                        still wins over ``JARVIS_STT_MODEL`` for STT

Nothing here downloads anything; it only describes and resolves choices.
"""
from __future__ import annotations

import importlib.util
import os
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------- TTS
# ``voices`` maps a JARVIS agent to the engine's native voice id.
TTS_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "edge-tts",
        "label": "Edge Neural TTS",
        "engine": "edge_tts",
        "default": True,
        "offline": False,
        "license": "Free, no key (Microsoft Edge voices)",
        "package": "edge-tts",
        "voices": {
            "jarvis": "en-GB-RyanNeural",
            "friday": "en-GB-SoniaNeural",
            "edith": "en-GB-LibbyNeural",
            "ultron": "en-GB-ThomasNeural",
        },
        "notes": (
            "Best free quality by a wide margin and zero setup: real neural "
            "British butler voice, ~300 ms to first byte. Needs internet."
        ),
    },
    {
        "id": "piper",
        "label": "Piper",
        "engine": "piper",
        "default": False,
        "offline": True,
        "license": "MIT",
        "package": "piper",
        "voices": {
            "jarvis": "en_GB-alan-medium",
            "friday": "en_GB-alba-medium",
            "edith": "en_US-amy-medium",
            "ultron": "en_GB-northern_english_male-medium",
        },
        "notes": (
            "Best offline quality that is still instant on a CPU. Needs the "
            "piper binary plus a ~60 MB .onnx voice (JARVIS_PIPER_VOICE)."
        ),
    },
    {
        "id": "kokoro",
        "label": "Kokoro 82M",
        "engine": "kokoro",
        "default": False,
        "offline": True,
        "license": "Apache-2.0",
        "package": "kokoro",
        "voices": {
            "jarvis": "bm_george",
            "friday": "bf_emma",
            "edith": "bf_isabella",
            "ultron": "am_michael",
        },
        "notes": (
            "Highest-quality fully offline model, but it drags in torch "
            "(~2 GB). Worth it only on a roomy machine."
        ),
    },
    {
        "id": "pyttsx3",
        "label": "pyttsx3 / eSpeak NG",
        "engine": "pyttsx3",
        "default": False,
        "offline": True,
        "license": "MPL-2.0 (eSpeak NG)",
        "package": "pyttsx3",
        "voices": {},
        "notes": "Last-resort fallback: always present, sounds robotic.",
    },
]

# --------------------------------------------------------------------- STT
# ``model`` is the faster-whisper size, so ``JARVIS_MODEL`` keeps working.
STT_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "groq-whisper-large-v3-turbo",
        "label": "Groq Whisper large-v3-turbo",
        "engine": "groq",
        "default": True,
        "offline": False,
        "license": "MIT (model) · Groq free tier (hosting)",
        "package": None,
        "key_provider": "groq",
        "model": "whisper-large-v3-turbo",
        "fallback": "faster-whisper-small.en",
        "notes": (
            "Primary engine: Groq hosts Whisper large-v3-turbo and returns a "
            "few-second clip in well under a second. Needs a free GROQ_API_KEY; "
            "falls back to the local model when offline or rate-limited."
        ),
    },
    {
        "id": "faster-whisper-small.en",
        "label": "Faster-Whisper small.en",
        "engine": "faster_whisper",
        "default": False,
        "offline": True,
        "license": "MIT",
        "package": "faster-whisper",
        "model": "small.en",
        "notes": (
            "Best free accuracy that stays realtime on a laptop CPU "
            "(int8, ~1 GB RAM). The local fallback when Groq is unreachable."
        ),
    },
    {
        "id": "faster-whisper-base.en",
        "label": "Faster-Whisper base.en",
        "engine": "faster_whisper",
        "default": False,
        "offline": True,
        "license": "MIT",
        "package": "faster-whisper",
        "model": "base.en",
        "notes": "Half the memory of small.en, noticeably more mishearings.",
    },
    {
        "id": "faster-whisper-tiny.en",
        "label": "Faster-Whisper tiny.en",
        "engine": "faster_whisper",
        "default": False,
        "offline": True,
        "license": "MIT",
        "package": "faster-whisper",
        "model": "tiny.en",
        "notes": "Fastest (~4x small.en) but weak on names and accents.",
    },
    {
        "id": "faster-whisper-medium.en",
        "label": "Faster-Whisper medium.en",
        "engine": "faster_whisper",
        "default": False,
        "offline": True,
        "license": "MIT",
        "package": "faster-whisper",
        "model": "medium.en",
        "notes": "Closer to large quality; ~3x slower than small.en on CPU.",
    },
    {
        "id": "faster-whisper-large-v3",
        "label": "Faster-Whisper large-v3",
        "engine": "faster_whisper",
        "default": False,
        "offline": True,
        "license": "MIT",
        "package": "faster-whisper",
        "model": "large-v3",
        "notes": "Most accurate and multilingual; wants a GPU.",
    },
    {
        "id": "vosk-small-en",
        "label": "Vosk small English",
        "engine": "vosk",
        "default": False,
        "offline": True,
        "license": "Apache-2.0",
        "package": "vosk",
        "model": "vosk-model-small-en-us-0.15",
        "notes": "Lightest (~50 MB, no torch); accuracy below base.en.",
    },
]


def _catalog(kind: str) -> List[Dict[str, Any]]:
    return TTS_CATALOG if kind == "tts" else STT_CATALOG


def _default_entry(kind: str) -> Dict[str, Any]:
    for entry in _catalog(kind):
        if entry.get("default"):
            return entry
    return _catalog(kind)[0]


def default_tts_id() -> str:
    return _default_entry("tts")["id"]


def default_stt_id() -> str:
    return _default_entry("stt")["id"]


def tts_model() -> str:
    """Selected TTS engine id (env ``JARVIS_TTS_MODEL`` wins)."""
    return (os.environ.get("JARVIS_TTS_MODEL") or default_tts_id()).strip()


def stt_model() -> str:
    """Selected STT engine id (env ``JARVIS_STT_MODEL`` wins)."""
    return (os.environ.get("JARVIS_STT_MODEL") or default_stt_id()).strip()


def get_tts(model_id: Optional[str] = None) -> Dict[str, Any]:
    wanted = (model_id or tts_model()).strip()
    for entry in TTS_CATALOG:
        if entry["id"] == wanted:
            return dict(entry)
    raise ValueError(
        f"unknown TTS model '{wanted}'; pick one of "
        + ", ".join(e["id"] for e in TTS_CATALOG)
    )


def get_stt(model_id: Optional[str] = None) -> Dict[str, Any]:
    wanted = (model_id or stt_model()).strip()
    for entry in STT_CATALOG:
        if entry["id"] == wanted:
            return dict(entry)
    raise ValueError(
        f"unknown STT model '{wanted}'; pick one of "
        + ", ".join(e["id"] for e in STT_CATALOG)
    )


def whisper_size(model_id: Optional[str] = None) -> str:
    """Resolve an STT id to a faster-whisper size.

    A bare size (``tiny``, ``base.en``) is accepted unchanged so existing
    ``JARVIS_MODEL`` values keep working. Remote engines (Groq) resolve to
    their local ``fallback`` so the offline path always has a usable size.
    """
    wanted = (model_id or os.environ.get("JARVIS_MODEL") or stt_model()).strip()
    for entry in STT_CATALOG:
        if entry["id"] == wanted:
            fallback = entry.get("fallback")
            if fallback and fallback != wanted:
                return whisper_size(fallback)
            return str(entry.get("model") or entry["id"])
    return wanted


def voice_for(agent: str, model_id: Optional[str] = None) -> Optional[str]:
    """Engine-native voice id for an agent, or None when the engine has none."""
    entry = get_tts(model_id)
    return (entry.get("voices") or {}).get((agent or "jarvis").lower())


def _installed(package: Optional[str]) -> bool:
    if not package:
        return False
    try:
        return importlib.util.find_spec(package.replace("-", "_")) is not None
    except (ImportError, ValueError):
        return False


def _key_configured(provider: Optional[str]) -> bool:
    """True when a provider API key is available (env wins over the vault)."""
    if not provider:
        return False
    try:
        from jarvis import keyvault

        return bool(keyvault.get_key(provider))
    except Exception:
        return bool(os.environ.get(provider.upper() + "_API_KEY"))


def engine_available(entry: Dict[str, Any]) -> bool:
    """An engine is usable when its package imports and its key is present."""
    package = entry.get("package")
    if package and not _installed(package):
        return False
    provider = entry.get("key_provider")
    if provider and not _key_configured(provider):
        return False
    return True


def list_voice_models(live: bool = False) -> Dict[str, Any]:
    """Return both catalogs, optionally annotated with what is installed."""
    out: Dict[str, Any] = {
        "default_tts": default_tts_id(),
        "default_stt": default_stt_id(),
        "selected_tts": tts_model(),
        "selected_stt": stt_model(),
    }
    for kind in ("tts", "stt"):
        rows = []
        for entry in _catalog(kind):
            row = dict(entry)
            if live:
                row["installed"] = engine_available(entry)
            rows.append(row)
        out[kind] = {"count": len(rows), "models": rows}
    out["note"] = (
        "Defaults are the best free options: Edge neural TTS (online, no key) "
        "and Groq Whisper large-v3-turbo (online, free key) with "
        "faster-whisper small.en as the offline fallback."
    )
    return out
