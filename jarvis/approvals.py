"""One-shot approval queue for irreversible host actions.

Deleting a file, uninstalling an app or shutting the PC down must not happen
because a model inferred it. Such an action is parked here, the assistant asks
for confirmation out loud, and only an explicit yes - a spoken "confirm" or a
tap in the HUD - runs it. Anything else (silence, a new command, a timeout)
drops it.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("jarvis.approvals")

TTL_SECONDS = 120.0

_AFFIRMATIVE = {
    "yes", "yeah", "yep", "sure", "confirm", "confirmed", "do it", "go ahead",
    "proceed", "affirmative", "ok", "okay", "yes sir", "please do",
}
_NEGATIVE = {
    "no", "nope", "cancel", "abort", "stop", "forget it", "never mind",
    "nevermind", "don't", "do not", "negative", "not now", "no thanks",
    "leave it", "don't do it",
}

_LOCK = threading.Lock()
_PENDING: Dict[str, Any] = {"tool": "", "args": None, "label": "", "at": 0.0}


def is_affirmative(text: str) -> bool:
    clean = " ".join(str(text or "").lower().strip().rstrip(".!").split())
    return clean in _AFFIRMATIVE


def is_negative(text: str) -> bool:
    clean = " ".join(str(text or "").lower().strip().rstrip(".!").split())
    return clean in _NEGATIVE


def needs_confirmation(tool: str, args: Dict[str, Any]) -> bool:
    """Ask before anything that destroys data or takes the machine down."""
    try:
        from jarvis import settings

        if not settings.flag("confirm_destructive", True):
            return False
    except Exception:
        pass

    from jarvis.tools.pc_control import DANGEROUS_SHELL

    action = str((args or {}).get("action") or "").lower()
    if tool in ("pc_control", "pc", "host", "pc_automation"):
        if action in ("delete_file", "uninstall_app", "shutdown", "restart",
                      "kill_process", "empty_recycle_bin"):
            return True
        if action in ("run_powershell", "run_command"):
            command = str(args.get("command") or args.get("target") or args.get("text") or "")
            return bool(DANGEROUS_SHELL.search(command))
        if action == "workflow":
            steps = args.get("steps") or []
            if isinstance(steps, str):
                try:
                    import json

                    steps = json.loads(steps)
                except Exception:
                    steps = []
            for step in steps if isinstance(steps, list) else []:
                if isinstance(step, dict) and needs_confirmation(str(step.get("tool") or "pc_control"), step):
                    return True
    if tool == "workflow":
        steps = (args or {}).get("steps") or []
        return any(isinstance(s, dict) and needs_confirmation(str(s.get("tool") or "pc_control"), s) for s in steps)
    return False


def request(tool: str, args: Dict[str, Any], label: str = "") -> Dict[str, Any]:
    """Park an action until the user says yes."""
    with _LOCK:
        _PENDING.update({"tool": tool, "args": dict(args or {}), "label": label, "at": time.time()})
    action = str((args or {}).get("action") or tool)
    target = str((args or {}).get("path") or (args or {}).get("target") or (args or {}).get("package") or "")
    what = " ".join(x for x in (action.replace("_", " "), target) if x).strip()
    return {
        "ok": True,
        "pending": True,
        "action": action,
        "message": "I am about to {0}. That cannot be undone, so say confirm to proceed or cancel to stop.".format(what or "do that"),
    }


def pending() -> Dict[str, Any]:
    with _LOCK:
        if _PENDING["args"] and (time.time() - float(_PENDING["at"] or 0)) <= TTL_SECONDS:
            return {"pending": True, "tool": _PENDING["tool"], "args": dict(_PENDING["args"] or {}),
                    "label": _PENDING["label"], "age": int(time.time() - _PENDING["at"])}
        return {"pending": False}


def cancel(reason: str = "cancelled") -> Dict[str, Any]:
    with _LOCK:
        had = bool(_PENDING["args"])
        _PENDING.update({"tool": "", "args": None, "label": "", "at": 0.0})
    return {"ok": True, "cancelled": had, "speech": "Cancelled, sir. Nothing was changed." if had else "There is nothing waiting, sir."}


def confirm() -> Dict[str, Any]:
    """Run the parked action exactly once."""
    with _LOCK:
        tool, args = _PENDING["tool"], _PENDING["args"]
        _PENDING.update({"tool": "", "args": None, "label": "", "at": 0.0})
    if not args:
        return {"ok": False, "speech": "There is nothing waiting for confirmation, sir."}

    from jarvis.tools.base import get_default_registry

    exec_args = dict(args)
    exec_args["confirm"] = True
    res = get_default_registry().execute(tool or "pc_control", args=exec_args, confirmed=True)
    result = res.get("result") or {"ok": res.get("ok"), "error": res.get("error")}
    if isinstance(result, dict) and result.get("ok") is False:
        try:
            from jarvis import pc_intents

            speech = pc_intents.summarise([result]) or "It failed, sir."
        except Exception:
            speech = "It failed, sir: {0}".format(result.get("error") or "unknown error")
        return {"ok": False, "result": result, "speech": speech}

    try:
        from jarvis import pc_intents

        speech = pc_intents.summarise([result]) or "Done, sir."
    except Exception:
        speech = "Done, sir."
    return {"ok": True, "result": result, "speech": speech}
