"""Vision backend: lets the assistant look at a camera frame.

The headset's passthrough camera is not exposed to web pages (WebXR takes the
camera over), so "eyes" come from a camera the page can open: the PC webcam in
the HUD, or the headset camera in the 2D browser view.

Models:
  * Groq ``qwen/qwen3.8-27b`` - vision capable, ~0.5 s, same key as the STT.
  * Gemini 2.5 / 3.5 Flash - vision capable, used when the Groq model is
    unavailable or the daily Gemini quota is spent.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from typing import Optional, Tuple

GROQ_VISION_MODEL = "qwen/qwen3.8-27b"
GROQ_VISION_FALLBACK = ("qwen/qwen3.8-27b",)
# Gemini is the primary vision brain. The free tier meters the daily limit PER
# MODEL, so the chain stacks: 3.5 Flash -> 3.5 Flash Lite -> 3.1 Flash Lite ->
# 3 Flash Preview -> 2.5 Flash.
GEMINI_VISION_MODELS = (
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
)

DEFAULT_PROMPT = (
    "You are the eyes of a voice assistant. Describe what the camera sees in one "
    "or two short spoken sentences: the room, the people, the objects and anything "
    "worth noticing. No markdown, no lists."
)


def _ollama_describe(
    image: bytes,
    prompt: str,
    timeout: float = 90.0,
) -> Tuple[Optional[str], Optional[str]]:
    """Local eyes: Gemma 3 4B reads the frame through Ollama. No cloud at all."""
    from jarvis import ollama_local

    if not ollama_local.available():
        raise RuntimeError("Ollama is not running on this machine")

    answer = ollama_local.chat(
        prompt,
        system=ollama_local.VISION_SYSTEM_PROMPT,
        images=[base64.b64encode(image).decode("ascii")],
        max_tokens=int(ollama_local._setting("ollama_vision_tokens", 160) or 160),
        temperature=0.2,
        timeout=timeout,
    )
    if not answer:
        raise RuntimeError(ollama_local.last_error() or "the local vision model returned nothing")
    return answer, "local:" + ollama_local.vision_model_name()


def _as_data_url(image: bytes, mime: str = "image/jpeg") -> str:
    return "data:{0};base64,{1}".format(mime, base64.b64encode(image).decode("ascii"))


def _groq_describe(data_url: str, prompt: str, timeout: float = 30.0) -> Tuple[Optional[str], Optional[str]]:
    from jarvis import llm

    key = llm.groq_key()
    if not key:
        return None, None

    payload = {
        "model": GROQ_VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        "max_tokens": 220,
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        llm.GROQ_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": llm.USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise RuntimeError("Groq vision HTTP {0}: {1}".format(exc.code, detail)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Groq vision unreachable: {0}".format(exc.reason)) from exc

    choices = data.get("choices") or []
    if not choices:
        return None, None
    message = choices[0].get("message") or {}
    text = (message.get("content") or "").strip()
    return (text or None), ("groq:" + GROQ_VISION_MODEL)


def _gemini_describe(data_url: str, prompt: str, timeout: float = 30.0) -> Tuple[Optional[str], Optional[str]]:
    """Ask Gemini through the native generateContent endpoint (inline image)."""
    from jarvis import gemini

    key = gemini.gemini_key()
    if not key:
        return None, None

    header, _, encoded = data_url.partition(",")
    mime = "image/jpeg"
    if header.startswith("data:"):
        mime = header[5:].split(";")[0] or mime

    cooldowns = gemini.cooldowns()
    errors = []

    for model in GEMINI_VISION_MODELS:
        if model in cooldowns:
            errors.append("gemini {0}: daily quota spent".format(model))
            continue

        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime, "data": encoded}},
                ],
            }],
            "generationConfig": {"maxOutputTokens": 220},
        }
        request = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models/{0}:generateContent".format(model),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-goog-api-key": key,
                "Content-Type": "application/json",
                "User-Agent": gemini.USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            errors.append("gemini {0}: HTTP {1}".format(model, exc.code))
            if exc.code == 429:
                gemini._note_cooldown(model, gemini._parse_retry_hint(detail) or 3600)
            continue
        except Exception as exc:
            errors.append("gemini {0}: {1}".format(model, exc))
            continue

        candidates = data.get("candidates") or []
        if not candidates:
            errors.append("gemini {0}: no answer".format(model))
            continue
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = " ".join(str(p.get("text", "")) for p in parts if p.get("text")).strip()
        if text:
            return text, ("gemini:" + model)

    if errors:
        raise RuntimeError("; ".join(errors))
    return None, None


def describe_image(
    image: bytes,
    prompt: Optional[str] = None,
    mime: str = "image/jpeg",
    timeout: float = 30.0,
) -> dict:
    """Describe an image. Returns ``{ok, description, engine, error}``."""
    prompt = prompt or DEFAULT_PROMPT
    started = time.time()

    try:
        from jarvis import settings as _settings

        if not _settings.flag("brain_enabled", True):
            return {"ok": False, "description": "", "engine": None,
                    "error": "brain is switched off - no vision model was contacted",
                    "elapsed_ms": 0}
    except Exception:
        pass

    if not image:
        return {"ok": False, "description": "", "engine": None,
                "error": "no image data", "elapsed_ms": 0}

    data_url = _as_data_url(image, mime)

    try:
        from jarvis import aimode

        local_only = aimode.mode() == "local"
    except Exception:
        local_only = False

    errors = []
    chain = []
    if local_only:
        # Local mode means local eyes. If the local model cannot see, the
        # assistant says so instead of quietly sending the frame to Gemini.
        chain.append(("local", lambda url, text, tmo: _ollama_describe(image, text, tmo)))
    else:
        try:
            from jarvis import settings as _settings

            if _settings.flag("gemini_enabled", True):
                chain.append(("gemini", _gemini_describe))
        except Exception:
            chain.append(("gemini", _gemini_describe))
        chain.append(("groq", _groq_describe))

    for name, fn in chain:
        try:
            text, engine = fn(data_url, prompt, timeout)
        except Exception as exc:
            errors.append("{0}: {1}".format(name, exc))
            continue
        if text:
            return {
                "ok": True,
                "description": text.strip(),
                "engine": engine,
                "mode": "local" if local_only else "cloud",
                "error": None,
                "errors": errors,
                "elapsed_ms": int((time.time() - started) * 1000),
            }
        errors.append("{0}: no answer".format(name))

    return {
        "ok": False,
        "description": "",
        "engine": None,
        "mode": "local" if local_only else "cloud",
        "error": "; ".join(errors) or "no vision backend available",
        "errors": errors,
        "elapsed_ms": int((time.time() - started) * 1000),
    }
