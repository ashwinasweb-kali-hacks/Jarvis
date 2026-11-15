"""Local AI brain: Ollama + Qwen3.5 4B, running on this machine.

Nothing here leaves the PC. The module is deliberately defensive: Ollama may
not be installed, may not be running, or may not have the model pulled yet, and
every one of those states has to be survivable without breaking the voice
pipeline.

The service is installed outside the project on purpose (``E:\\JARVIS\\ollama``)
so the model weights never land on the small system drive. Override the paths
with ``JARVIS_OLLAMA_URL`` / ``JARVIS_OLLAMA_MODEL`` / ``JARVIS_OLLAMA_DIR``.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger("jarvis.ollama_local")

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3.5:4b"
DEFAULT_VISION_MODEL = "gemma3:4b"
DEFAULT_KEEP_ALIVE = "30m"
DEFAULT_DIR = r"E:\JARVIS\ollama"

# A health probe every 2 s is cheap, but not on every single token, so the
# answer is cached briefly.
_PROBE_TTL = 2.0
_lock = threading.Lock()
_probe: Dict[str, Any] = {"at": 0.0, "ok": False, "version": "", "error": ""}
_last_error = ""


# --------------------------------------------------------------------------- config
def _setting(key: str, default: Any = None) -> Any:
    try:
        from jarvis import settings

        return settings.get(key, default)
    except Exception:
        return default


def base_url() -> str:
    env = os.environ.get("JARVIS_OLLAMA_URL", "").strip()
    if env:
        return env.rstrip("/")
    value = str(_setting("ollama_url", DEFAULT_URL) or DEFAULT_URL).strip()
    return (value or DEFAULT_URL).rstrip("/")


def model_name() -> str:
    env = os.environ.get("JARVIS_OLLAMA_MODEL", "").strip()
    if env:
        return env
    return str(_setting("ollama_model", DEFAULT_MODEL) or DEFAULT_MODEL).strip()


def vision_model_name() -> str:
    """The local eyes: a multimodal model that also reads text in pictures."""
    env = os.environ.get("JARVIS_OLLAMA_VISION_MODEL", "").strip()
    if env:
        return env
    return str(_setting("ollama_vision_model", DEFAULT_VISION_MODEL) or DEFAULT_VISION_MODEL).strip()


def keep_alive() -> str:
    return str(_setting("ollama_keep_alive", DEFAULT_KEEP_ALIVE) or DEFAULT_KEEP_ALIVE)


# A 6 GB card holds one 4B model, so vision and text cannot both stay resident.
# After a frame, text questions keep using the vision model for a while: one
# model, no 6-10 s swap per turn.
_STICKY_SECONDS = 90.0
_last_vision_at = 0.0


def preferred_model(vision: bool = False) -> str:
    """Which local model answers this turn, and why."""
    global _last_vision_at
    eyes = vision_model_name()
    text = model_name()
    if vision:
        _last_vision_at = time.time()
        return eyes
    if (time.time() - _last_vision_at) < _STICKY_SECONDS:
        return eyes
    # After the sticky window, stay on whichever model is already resident: a
    # swap costs 6-10 s, and both models answer a plain question in ~0.3 s.
    try:
        tags = {str(m.get("name") or m.get("model") or "") for m in list_loaded(timeout=1.5)}
    except Exception:
        tags = set()
    if eyes in tags and text not in tags:
        return eyes
    return text


def _remember_vision() -> None:
    global _last_vision_at
    _last_vision_at = time.time()


def _think() -> bool:
    """Qwen3.5 reasons before answering unless told not to.

    A hidden chain of thought would eat the whole token budget and return an
    empty ``content``, so thinking is off by default: it is the difference
    between a 0.5 s spoken answer and a silent 2 s timeout.
    """
    raw = _setting("ollama_think", False)
    return bool(raw) if isinstance(raw, bool) else str(raw).strip().lower() in ("1", "true", "yes", "on")


def install_dir() -> Path:
    return Path(os.environ.get("JARVIS_OLLAMA_DIR", DEFAULT_DIR))


def last_error() -> str:
    return _last_error


# --------------------------------------------------------------------------- transport
def _request(path: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
    """One JSON call against the local API. Raises on transport errors."""
    url = base_url() + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return json.loads(raw) if raw.strip() else {}


def _stream(path: str, payload: Dict[str, Any], timeout: float) -> Iterator[Dict[str, Any]]:
    """Yield decoded NDJSON chunks from a streaming Ollama endpoint."""
    url = base_url() + path
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for line in resp:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line.decode("utf-8", "replace"))
            except Exception:
                continue


# --------------------------------------------------------------------------- status
def version(refresh: bool = False) -> str:
    return str(status(refresh=refresh).get("version") or "")


def available(refresh: bool = False) -> bool:
    """True when the Ollama service answers. Cached for a couple of seconds."""
    return bool(status(refresh=refresh).get("available"))


def status(refresh: bool = False) -> Dict[str, Any]:
    global _last_error
    now = time.time()
    with _lock:
        fresh = (now - float(_probe.get("at") or 0.0)) < _PROBE_TTL
        if fresh and not refresh:
            ok = bool(_probe.get("ok"))
            ver = str(_probe.get("version") or "")
            err = str(_probe.get("error") or "")
        else:
            ok, ver, err = False, "", ""
            try:
                data = _request("/api/version", timeout=1.5)
                ver = str(data.get("version") or "")
                ok = True
                _last_error = ""
            except Exception as exc:  # connection refused, timeout, DNS ...
                err = _friendly_error(exc)
                _last_error = err
            _probe.update({"at": now, "ok": ok, "version": ver, "error": err})

    models: List[str] = []
    loaded: List[Dict[str, Any]] = []
    if ok:
        try:
            models = list_models(timeout=2.0)
        except Exception:
            models = []
        try:
            loaded = list_loaded(timeout=2.0)
        except Exception:
            loaded = []

    wanted = model_name()
    present = _has_model(wanted, models)
    eyes = vision_model_name()

    active = None
    for item in loaded:
        tag = str(item.get("name") or item.get("model") or "")
        if tag in (wanted, eyes):
            active = item
            break

    return {
        "available": ok,
        "version": ver,
        "url": base_url(),
        "model": wanted,
        "model_present": bool(present),
        "vision_model": eyes,
        "vision_present": _has_model(eyes, models),
        "models": models,
        "loaded": loaded,
        "active": active,
        "gpu": bool(active and float(active.get("size_vram") or 0) > 0),
        "keep_alive": keep_alive(),
        "install_dir": str(install_dir()),
        "installed": (install_dir() / "ollama.exe").exists() or bool(shutil.which("ollama")),
        "error": err,
        "checked_at": int(now),
    }


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    if isinstance(exc, urllib.error.URLError) or "refused" in text.lower():
        return "Ollama is not running (127.0.0.1:11434 refused the connection)."
    if isinstance(exc, TimeoutError) or "timed out" in text.lower():
        return "Ollama did not answer in time."
    return text or exc.__class__.__name__


def list_models(timeout: float = 3.0) -> List[str]:
    data = _request("/api/tags", timeout=timeout)
    out = []
    for item in data.get("models") or []:
        name = str(item.get("name") or item.get("model") or "").strip()
        if name:
            out.append(name)
    return out


def list_loaded(timeout: float = 3.0) -> List[Dict[str, Any]]:
    data = _request("/api/ps", timeout=timeout)
    return [m for m in (data.get("models") or []) if isinstance(m, dict)]


def _has_model(name: str, models: List[str]) -> bool:
    """Ollama reports full tags (``gemma3:4b``); accept a tag or a family match."""
    if not name:
        return False
    base = name.split(":")[0]
    return any(m == name or m == base or m.startswith(base + ":") for m in models)


# --------------------------------------------------------------------------- lifecycle
def load(model: Optional[str] = None, timeout: float = 120.0) -> Dict[str, Any]:
    """Load the model into memory (VRAM when possible) without generating."""
    name = model or model_name()
    last = ""
    # Ollama frees a model asynchronously, so an immediate load after an unload
    # can lose the race. One short retry makes the HUD's toggle deterministic.
    for attempt in range(2):
        try:
            _request("/api/generate", {"model": name, "prompt": "", "keep_alive": keep_alive()}, timeout=timeout)
            return {"ok": True, "model": name, "loaded": True, "keep_alive": keep_alive()}
        except Exception as exc:
            last = _friendly_error(exc)
            if attempt == 0:
                time.sleep(1.5)
    return {"ok": False, "model": name, "error": last}


def unload(model: Optional[str] = None, timeout: float = 30.0) -> Dict[str, Any]:
    """Free the model from memory until the next request."""
    name = model or model_name()
    try:
        _request("/api/generate", {"model": name, "prompt": "", "keep_alive": 0}, timeout=timeout)
        return {"ok": True, "model": name, "loaded": False}
    except Exception as exc:
        return {"ok": False, "model": name, "error": _friendly_error(exc)}


def ensure_warm(background: bool = True, model: Optional[str] = None) -> Dict[str, Any]:
    """Keep the model resident so the first spoken question is not a cold start."""
    st = status()
    name = model or st["model"]
    if not st["available"]:
        return {"ok": False, "warm": False, "reason": st["error"] or "Ollama is not running"}
    if not _has_model(name, st.get("models") or []):
        return {"ok": False, "warm": False, "reason": "model %s is not pulled" % name}
    # One model can be resident; whichever it is, it is warm enough to answer.
    if st.get("loaded"):
        resident = st.get("active") or st["loaded"][0]
        return {"ok": True, "warm": True,
                "model": resident.get("name") or resident.get("model") or name}
    if background:
        threading.Thread(target=lambda: load(name), name="ollama-warm", daemon=True).start()
        return {"ok": True, "warm": False, "warming": True, "model": name}
    res = load(name)
    res["warm"] = bool(res.get("ok"))
    return res


def start_service() -> Dict[str, Any]:
    """Start Ollama from the E: install if nothing is listening."""
    if available(refresh=True):
        return {"ok": True, "already_running": True, "version": version()}
    exe = install_dir() / "ollama.exe"
    if not exe.exists():
        found = shutil.which("ollama")
        if not found:
            return {"ok": False, "error": "Ollama is not installed under E:\\JARVIS\\ollama."}
        exe = Path(found)
    env = dict(os.environ)
    env.setdefault("OLLAMA_MODELS", str(install_dir() / "models"))
    env.setdefault("OLLAMA_HOST", base_url().replace("http://", ""))
    logs = install_dir().parent / "logs"
    try:
        logs.mkdir(parents=True, exist_ok=True)
        out = open(logs / "ollama.out.log", "ab")
        subprocess.Popen(
            [str(exe), "serve"],
            stdout=out,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    for _ in range(30):
        if available(refresh=True):
            return {"ok": True, "started": True, "version": version()}
        time.sleep(1.0)
    return {"ok": False, "error": "Ollama did not come up on " + base_url()}


# --------------------------------------------------------------------------- inference
SYSTEM_PROMPT = (
    "You are JARVIS, a calm, dry British AI butler who addresses the user as 'sir'. "
    "You run locally on the user's own machine, so you have no internet of your own. "
    "Reply with spoken dialogue only: no markdown, no lists, no asterisks, no preamble. "
    "Keep it to one concise spoken sentence under 20 words."
)


def _clean(text: str) -> str:
    text = (text or "").replace("*", "").replace("`", "").strip()
    for a, b in (("\u2014", ", "), ("\u2013", "-"), ("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"')):
        text = text.replace(a, b)
    return text


VISION_SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S., the eyes and voice of a hands-free assistant. You are "
    "looking through the user's camera. Say what you actually see in one short "
    "spoken sentence, then answer their question if there is one. Never invent "
    "objects that are not in the picture. No markdown."
)


def chat(
    text: str,
    system: Optional[str] = None,
    max_tokens: int = 90,
    temperature: float = 0.3,
    timeout: float = 12.0,
    history: Optional[List[Dict[str, str]]] = None,
    images: Optional[List[str]] = None,
    model: Optional[str] = None,
) -> Optional[str]:
    """One blocking completion. Returns None when the local model is unavailable.

    ``images`` is a list of base64 JPEG/PNG payloads (no data: prefix). When a
    frame is supplied the multimodal model answers, so a visual turn costs one
    local call - describe and answer in one pass.
    """
    global _last_error
    frames = [i for i in (images or []) if i]
    if model:
        chosen = model
        if frames:
            _remember_vision()
    else:
        chosen = preferred_model(vision=bool(frames))
    payload: Dict[str, Any] = {
        "model": chosen,
        "messages": [{"role": "system", "content": system or (VISION_SYSTEM_PROMPT if frames else SYSTEM_PROMPT)}]
        + [m for m in (history or []) if m.get("role") in ("user", "assistant")]
        + [{"role": "user", "content": text, **({"images": frames} if frames else {})}],
        "stream": False,
        "keep_alive": keep_alive(),
        "think": _think(),
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    try:
        data = _request("/api/chat", payload, timeout=timeout)
    except Exception as exc:
        _last_error = _friendly_error(exc)
        logger.debug("Ollama chat failed: %s", _last_error)
        return None

    msg = data.get("message") or {}
    answer = _clean(str(msg.get("content") or ""))
    if not answer:
        # A reasoning model can spend the whole budget in ``thinking`` and return
        # an empty ``content``. That is a failed turn for a spoken assistant, not
        # an answer: report it so the caller can say so honestly.
        _last_error = "the local model returned an empty answer"
        return None
    _last_error = ""
    return answer


def chat_stream(
    text: str,
    system: Optional[str] = None,
    max_tokens: int = 120,
    temperature: float = 0.3,
    timeout: float = 30.0,
    history: Optional[List[Dict[str, str]]] = None,
) -> Iterator[str]:
    """Yield answer fragments as the local model produces them."""
    global _last_error
    payload = {
        "model": model_name(),
        "messages": [{"role": "system", "content": system or SYSTEM_PROMPT}]
        + [m for m in (history or []) if m.get("role") in ("user", "assistant")]
        + [{"role": "user", "content": text}],
        "stream": True,
        "keep_alive": keep_alive(),
        "think": _think(),
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    try:
        for chunk in _stream("/api/chat", payload, timeout):
            if chunk.get("error"):
                _last_error = str(chunk["error"])
                return
            piece = ((chunk.get("message") or {}).get("content") or "")
            if piece:
                yield piece
            if chunk.get("done"):
                return
    except Exception as exc:
        _last_error = _friendly_error(exc)
        logger.debug("Ollama stream failed: %s", _last_error)
        return
