"""Gemini chat backend for the JARVIS brain.

The assistant talks to Gemini through Google's OpenAI-compatible endpoint so
the same client code works for Gemini, Groq and any other provider. Gemini 3.x
is a thinking model: without a hint it spends 2-4 seconds on reasoning tokens
before answering, which is too slow for a spoken HUD, so the request asks for
``reasoning_effort: none`` and falls back to a normal request if the endpoint
rejects it.

The free tier is strict - each model gets its own daily request quota (20/day
for this key on the 3.x models). When a model runs out the API answers HTTP 429
with a "retry in 23h..." hint, so the client records a cooldown for that model
and moves on to the next one (for example ``gemini-2.5-flash``) instead of
failing the whole request.

The API key lives in the key vault (provider ``gemini``); the environment
variable ``GEMINI_API_KEY`` overrides it.
"""
from __future__ import annotations

import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

GEMINI_CHAT_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
GEMINI_TIMEOUT_SECONDS = 3.5

# Ordered fallbacks in case the preferred model is unavailable or out of quota.
# The free tier meters the daily request limit PER MODEL, so a chain of Gemini
# models multiplies the number of questions the assistant can answer per day.
GEMINI_MODEL_CHAIN = (
    DEFAULT_GEMINI_MODEL,
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-3.8-flash",
    "gemini-flash-latest",
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# model -> unix time until which the model is skipped (quota / outage backoff)
_MODEL_COOLDOWN: Dict[str, float] = {}
_LAST_ERROR: Optional[str] = None
_LAST_MODEL: Optional[str] = None

# The cooldowns are kept on disk so a daemon restart does not waste a request on
# a model whose daily quota is already spent.
COOLDOWN_PATH = Path.home() / ".jarvis" / "gemini_cooldowns.json"


def _load_cooldowns() -> None:
    try:
        raw = json.loads(COOLDOWN_PATH.read_text(encoding="utf-8"))
        now = time.time()
        for model, until in raw.items():
            if isinstance(until, (int, float)) and until > now:
                _MODEL_COOLDOWN[model] = float(until)
    except Exception:
        pass


def _save_cooldowns() -> None:
    try:
        now = time.time()
        live = {model: until for model, until in _MODEL_COOLDOWN.items() if until > now}
        COOLDOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
        COOLDOWN_PATH.write_text(json.dumps(live, indent=1), encoding="utf-8")
    except Exception:
        pass


_load_cooldowns()


def gemini_key() -> Optional[str]:
    """Gemini API key from the environment or the key vault, if any."""
    for env_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = os.environ.get(env_name)
        if value and value.strip():
            return value.strip()

    try:
        from jarvis import keyvault

        value = keyvault.get_key("gemini") or keyvault.get_key("google")
    except Exception:
        value = None

    return value.strip() if value else None


def _parse_retry_hint(body: str) -> Optional[float]:
    """Seconds to wait before retrying, from a Google quota error."""
    match = re.search(r"retry in (\d+)h(\d+)m", body or "")
    if match:
        return int(match.group(1)) * 3600 + int(match.group(2)) * 60

    match = re.search(r'"retryDelay":\s*"(\d+)s"', body or "")
    if match:
        return float(match.group(1))

    match = re.search(r'retry in (\d+)s', body or "")
    if match:
        return float(match.group(1))

    return None


def _note_cooldown(model: str, seconds: float) -> None:
    _MODEL_COOLDOWN[model] = time.time() + max(60.0, seconds)
    _save_cooldowns()


def cooldowns() -> Dict[str, int]:
    """Models currently in cooldown, with the remaining seconds."""
    now = time.time()
    return {
        model: int(until - now)
        for model, until in _MODEL_COOLDOWN.items()
        if until > now
    }


def last_error() -> Optional[str]:
    return _LAST_ERROR


def last_model() -> Optional[str]:
    """The Gemini model that produced the most recent answer."""
    return _LAST_MODEL


def _post_chat(key: str, model: str, messages: List[Dict[str, Any]], temperature: float,
               max_tokens: int, timeout: float, fast: bool) -> str:
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if fast:
        # Skip the thinking phase: this is what takes the answer from ~4 s to ~1 s.
        payload["reasoning_effort"] = "none"

    request = urllib.request.Request(
        GEMINI_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")

    data = json.loads(raw)
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return (message.get("content") or "").strip()


def chat_gemini(
    prompt: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 256,
    timeout: float = GEMINI_TIMEOUT_SECONDS,
    fast: bool = True,
    models: Optional[List[str]] = None,
) -> Optional[str]:
    """Ask Gemini for an answer. Returns None when unavailable."""
    global _LAST_ERROR, _LAST_MODEL

    key = gemini_key()
    if not key:
        return None

    errors: List[str] = []

    messages: List[Dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    chain = list(models) if models else ([model] if model else list(GEMINI_MODEL_CHAIN))
    now = time.time()

    for candidate in chain:
        cooldown_until = _MODEL_COOLDOWN.get(candidate, 0.0)
        if cooldown_until > now:
            continue  # quota/outage backoff for this model

        try:
            answer = _post_chat(key, candidate, messages, temperature, max_tokens, timeout, fast)
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")
            except Exception:
                pass

            if exc.code == 400 and fast:
                # Older endpoints do not know reasoning_effort; retry normally.
                try:
                    answer = _post_chat(key, candidate, messages, temperature, max_tokens, timeout, False)
                except urllib.error.HTTPError as inner:
                    body = ""
                    try:
                        body = inner.read().decode("utf-8", "replace")
                    except Exception:
                        pass
                    if inner.code == 429:
                        _note_cooldown(candidate, _parse_retry_hint(body) or 3600)
                        _LAST_ERROR = "gemini {0}: quota exceeded".format(candidate)
                    continue
            elif exc.code == 429:
                _note_cooldown(candidate, _parse_retry_hint(body) or 3600)
                _LAST_ERROR = "gemini {0}: quota exceeded".format(candidate)
                continue  # another model has its own quota
            elif exc.code in (404, 503):
                _LAST_ERROR = "gemini {0}: HTTP {1}".format(candidate, exc.code)
                if exc.code == 503:
                    # Transient overload, not a quota problem: wait a moment.
                    _note_cooldown(candidate, 120)
                continue  # unknown model or overloaded, try the next one
            else:
                _LAST_ERROR = "gemini {0}: HTTP {1}".format(candidate, exc.code)
                return None
        except Exception as exc:
            # A timeout or a transport error must not end the chain: the next
            # model in the list is usually fine (the free tier hiccups).
            _LAST_ERROR = "gemini {0}: {1}".format(candidate, exc)
            errors.append(_LAST_ERROR)
            if isinstance(exc, (TimeoutError, socket.timeout)):
                _note_cooldown(candidate, 90)
            continue

        if answer:
            _LAST_ERROR = None
            _LAST_MODEL = candidate
            return answer

    return None


def chat_available() -> bool:
    """True when a Gemini key is configured."""
    return bool(gemini_key())
