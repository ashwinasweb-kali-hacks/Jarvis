"""Local / Cloud brain selection.

One persisted setting, ``ai_mode``, decides where every new request goes:

* ``local`` - Qwen3.5 4B through Ollama on this machine. No cloud call is made,
  ever: if the local model is unreachable the assistant says so instead of
  quietly spending Gemini quota.
* ``cloud`` - the existing Gemini / Groq chain, untouched.

The mode is written to ``~/.jarvis/settings.json`` so it survives restarts, and
the daemon reports both the mode and the live connection status.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from jarvis import ollama_local, settings

logger = logging.getLogger("jarvis.aimode")

MODES = ("local", "cloud")
DEFAULT_MODE = "cloud"


def mode() -> str:
    """The active mode, accepting only a known value."""
    raw = str(settings.get("ai_mode", DEFAULT_MODE) or DEFAULT_MODE).strip().lower()
    return raw if raw in MODES else DEFAULT_MODE


def is_local() -> bool:
    return mode() == "local"


def set_mode(value: str) -> Dict[str, Any]:
    """Switch modes. Returns the new state; refuses unknown values."""
    raw = str(value or "").strip().lower()
    if raw in ("on-device", "offline", "ollama", "qwen"):
        raw = "local"
    if raw in ("gemini", "online", "remote"):
        raw = "cloud"
    if raw not in MODES:
        return {"ok": False, "error": "ai_mode must be 'local' or 'cloud'", "mode": mode()}

    settings.set("ai_mode", raw)
    # Keep the local model resident the moment local mode is selected, so the
    # user's first question does not pay the cold-start cost.
    warm = None
    if raw == "local":
        try:
            warm = ollama_local.ensure_warm(background=True)
        except Exception as exc:  # never block the switch on a warm-up failure
            warm = {"ok": False, "error": str(exc)}
    return {"ok": True, "mode": raw, "warmup": warm, "status": status()}


def cloud_detail() -> Dict[str, Any]:
    """What the existing cloud chain can do right now."""
    gemini_ok = False
    gemini_err = ""
    try:
        from jarvis import gemini

        gemini_ok = bool(gemini.chat_available())
        gemini_err = gemini.last_error() or ""
    except Exception as exc:
        gemini_err = str(exc)
    groq_ok = False
    try:
        from jarvis import llm

        groq_ok = bool(llm.chat_available())
    except Exception:
        pass
    enabled = True
    gemini_enabled = True
    try:
        enabled = settings.flag("brain_enabled", True)
        gemini_enabled = settings.flag("gemini_enabled", True)
    except Exception:
        pass
    return {
        "ready": bool(enabled and ((gemini_ok and gemini_enabled) or groq_ok)),
        "gemini": gemini_ok,
        "gemini_enabled": gemini_enabled,
        "gemini_model": _gemini_model(),
        "gemini_error": gemini_err,
        "groq": groq_ok,
        "brain_enabled": enabled,
    }


def _gemini_model() -> str:
    try:
        import os

        from jarvis import gemini

        return os.environ.get("JARVIS_GEMINI_MODEL", gemini.DEFAULT_GEMINI_MODEL)
    except Exception:
        return ""


def status() -> Dict[str, Any]:
    """Everything the HUD needs to paint the Local / Cloud control honestly."""
    current = mode()
    local = ollama_local.status()
    cloud = cloud_detail()

    if current == "local":
        ready = bool(local["available"] and local["model_present"])
        if not local["available"]:
            reason = local["error"] or "Ollama is not running."
        elif not local["model_present"]:
            reason = "Model %s is not pulled yet." % local["model"]
        elif not local.get("vision_present"):
            reason = ("Text ready%s; eyes need %s (ollama pull %s)."
                      % (" (GPU)" if local.get("gpu") else " (CPU)", local.get("vision_model"), local.get("vision_model")))
        else:
            reason = ("Local model and eyes ready" + (" (GPU)" if local.get("gpu") else " (CPU)"))
    else:
        ready = bool(cloud["ready"])
        if not cloud["brain_enabled"]:
            reason = "The master brain switch is off."
        elif not cloud["gemini_enabled"] and not cloud["groq"]:
            reason = "Gemini is switched off and Groq is unavailable."
        elif not cloud["gemini"] and not cloud["groq"]:
            reason = cloud["gemini_error"] or "No cloud provider is reachable."
        else:
            reason = "Cloud model ready"

    return {
        "mode": current,
        "ready": ready,
        "reason": reason,
        "local": local,
        "cloud": cloud,
    }
