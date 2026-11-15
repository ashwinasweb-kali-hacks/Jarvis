"""OpenAI-compatible chat helpers used by the JARVIS brain.

Why this exists: the voice HUD needs an answer in well under a second, and the
brain's previous chain (OAuth CLI, Gemini, local models) could not answer at
all on this machine. Groq's hosted chat models answer in a few hundred
milliseconds and the key already lives in the key vault, so it becomes the fast
path while the OpenCode CLI stays as the fallback.

Only the standard library is used (urllib) so the daemon keeps working without
extra dependencies.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_CHAT_MODEL = "openai/gpt-oss-120b"
GROQ_TIMEOUT_SECONDS = 20.0

# Groq's edge rejects header-less urllib calls with a Cloudflare 403, so the
# request has to look like a normal browser client.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Model fallbacks in order; the first one the account can use wins.
GROQ_MODEL_CHAIN = (
    DEFAULT_GROQ_CHAT_MODEL,
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
    "allam-2-7b",
)


def groq_key() -> Optional[str]:
    """Groq API key from the vault (env ``GROQ_API_KEY`` wins), if any."""
    try:
        from jarvis import keyvault

        value = keyvault.get_key("groq")
    except Exception:
        value = os.environ.get("GROQ_API_KEY")
    return value.strip() if value else None


def _post_chat(key: str, model: str, messages: List[Dict[str, Any]], temperature: float,
               max_tokens: int, timeout: float) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    request = urllib.request.Request(
        GROQ_CHAT_URL,
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


def chat_groq(
    prompt: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 120,
    timeout: float = GROQ_TIMEOUT_SECONDS,
    models: Optional[List[str]] = None,
) -> Optional[str]:
    """Ask Groq for a one-line answer. Returns None when unavailable."""
    global _LAST_MODEL

    key = groq_key()
    if not key:
        return None

    messages: List[Dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    chain = list(models) if models else ([model] if model else list(GROQ_MODEL_CHAIN))
    last_error: Optional[Exception] = None

    for candidate in chain:
        try:
            answer = _post_chat(key, candidate, messages, temperature, max_tokens, timeout)
        except urllib.error.HTTPError as exc:
            last_error = RuntimeError("Groq chat HTTP {0}".format(exc.code))
            if exc.code in (400, 404):
                continue  # model unknown for this account, try the next one
            return None
        except Exception as exc:
            last_error = exc
            return None

        if answer:
            _LAST_MODEL = candidate
            return answer

    if last_error:
        return None
    return None


def chat_available() -> bool:
    """True when a Groq key is configured."""
    return bool(groq_key())


_LAST_MODEL: Optional[str] = None


def last_model() -> Optional[str]:
    """The Groq model that produced the most recent answer."""
    return _LAST_MODEL
