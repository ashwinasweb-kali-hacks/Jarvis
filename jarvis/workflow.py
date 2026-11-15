"""Multi-step automation workflows.

A workflow is a list of steps the assistant can run as one spoken command
("open Chrome, search for the weather, and read me the first result"). Each step
names a tool - the host controller, the browser, screen awareness or a raw
shell - and the whole run is logged, verified and stop-on-failure.

Destructive steps (delete, uninstall, power off, killing processes, dangerous
PowerShell) are collected and the run stops before them with
``needs_confirmation``. Only an explicit yes - :func:`confirm` - executes them.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.workflow")

MAX_STEPS = 30
STEP_TIMEOUT = 60

# Host actions that must be confirmed before they run.
DESTRUCTIVE_ACTIONS = {
    "delete_file", "delete_path", "uninstall_app", "shutdown", "restart", "sleep",
    "hibernate", "kill_process", "empty_recycle_bin", "format_drive",
}

DANGEROUS_SHELL = re.compile(
    r"(?i)\b(format|diskpart|del\s+/[sq]|rmdir\s+/s|rd\s+/s|remove-item\s+-recurse|"
    r"remove-item\s+-force|reg\s+delete|bcdedit|cipher\s+/w|vssadmin\s+delete|"
    r"shutdown|stop-computer|restart-computer|set-mppreference|takeown|icacls\s+.*\/reset)\b"
)

_PENDING: Dict[str, Any] = {"steps": None, "at": 0.0, "label": ""}
_PENDING_TTL = 120.0
_PENDING_LOCK = threading.Lock()


def _setting(key: str, default: Any = None) -> Any:
    try:
        from jarvis import settings

        return settings.get(key, default)
    except Exception:
        return default


def _flag(key: str, default: bool = True) -> bool:
    try:
        from jarvis import settings

        return settings.flag(key, default)
    except Exception:
        return default


def needs_confirmation(step: Dict[str, Any]) -> bool:
    """Does this step change or destroy something that cannot be undone?"""
    if not _flag("confirm_destructive", True):
        return False
    tool = str(step.get("tool") or "pc_control").lower()
    action = str(step.get("action") or "").lower()

    if tool in ("pc", "pc_control", "host"):
        if action in DESTRUCTIVE_ACTIONS:
            return True
        if action in ("run_powershell", "run_command", "shell"):
            command = str(step.get("command") or step.get("target") or step.get("text") or "")
            return bool(DANGEROUS_SHELL.search(command))
    if tool == "shell":
        command = str(step.get("command") or step.get("target") or "")
        return bool(DANGEROUS_SHELL.search(command))
    return False


def _run_pc(step: Dict[str, Any]) -> Dict[str, Any]:
    from jarvis.tools.base import get_default_registry

    args = {k: v for k, v in step.items() if k not in ("tool", "parallel", "_confirmed")}
    # A workflow the user has already approved must not stall on the tool's own
    # per-action confirmation, so the approval travels with the step.
    if step.get("_confirmed"):
        args.setdefault("confirm", True)
    reg = get_default_registry()
    res = reg.execute("pc_control", args=args, confirmed=True)
    if res.get("result") is not None:
        out = dict(res["result"])
        out["_ok"] = bool(res.get("ok")) and bool(out.get("ok", True))
        return out
    return {"ok": bool(res.get("ok")), "error": res.get("error"), "_ok": bool(res.get("ok"))}


def _run_browser(step: Dict[str, Any]) -> Dict[str, Any]:
    from jarvis import browser

    args = {k: v for k, v in step.items() if k not in ("tool", "action")}
    out = browser.run(str(step.get("action") or ""), **args)
    out["_ok"] = bool(out.get("ok"))
    return out


def _run_screen(step: Dict[str, Any]) -> Dict[str, Any]:
    from jarvis import screen

    action = str(step.get("action") or "read").lower()
    if action in ("read", "snapshot", "describe"):
        data = screen.snapshot(with_ocr=True)
        if action == "describe":
            return {"ok": True, "spoken": screen.describe(data), "window": data.get("window"), "_ok": True}
        return {"ok": True, "window": data.get("window"), "element_count": data.get("element_count"),
                "text": (data.get("text") or "")[:1200], "_ok": True}
    if action == "click":
        out = screen.click_element(str(step.get("target") or step.get("text") or ""))
    elif action == "vision":
        out = screen.describe_with_vision(step.get("prompt"))
    else:
        return {"ok": False, "error": "unknown screen action %r" % action, "_ok": False}
    out["_ok"] = bool(out.get("ok"))
    return out


def _run_shell(step: Dict[str, Any]) -> Dict[str, Any]:
    from jarvis.tools.pc_control import run_powershell

    command = str(step.get("command") or step.get("target") or "")
    out = run_powershell(command, timeout=int(step.get("timeout") or 45))
    out["_ok"] = bool(out.get("ok"))
    return out


def _run_wait(step: Dict[str, Any]) -> Dict[str, Any]:
    seconds = max(0.0, min(float(step.get("seconds") or 1), 30.0))
    time.sleep(seconds)
    return {"ok": True, "waited": seconds, "_ok": True}


RUNNERS = {
    "pc": _run_pc, "pc_control": _run_pc, "host": _run_pc,
    "browser": _run_browser,
    "screen": _run_screen,
    "shell": _run_shell,
    "powershell": _run_shell,
    "wait": _run_wait,
}


def _run_one(step: Dict[str, Any]) -> Dict[str, Any]:
    tool = str(step.get("tool") or "pc").lower()
    fn = RUNNERS.get(tool)
    label = "%s/%s" % (tool, step.get("action") or "")
    if not fn:
        return {"ok": False, "_ok": False, "step": label, "error": "unknown tool %r" % tool}
    started = time.time()
    try:
        out = fn(step)
    except Exception as exc:
        logger.exception("workflow step failed: %s", label)
        out = {"ok": False, "_ok": False, "error": str(exc)}
    out.setdefault("_ok", bool(out.get("ok")))
    out["step"] = label
    out["elapsed_ms"] = int((time.time() - started) * 1000)
    return out


def pending() -> Dict[str, Any]:
    with _PENDING_LOCK:
        if _PENDING["steps"] and (time.time() - _PENDING["at"]) <= _PENDING_TTL:
            return {"pending": True, "label": _PENDING["label"], "steps": _PENDING["steps"]}
        return {"pending": False}


def clear_pending() -> None:
    with _PENDING_LOCK:
        _PENDING.update({"steps": None, "at": 0.0, "label": ""})


def confirm() -> Dict[str, Any]:
    """Run the workflow that was waiting for a yes."""
    with _PENDING_LOCK:
        steps = _PENDING["steps"]
        stale = not steps or (time.time() - _PENDING["at"]) > _PENDING_TTL
        if stale:
            # Clear inline: calling clear_pending() here would re-enter the
            # non-reentrant lock and deadlock the daemon thread.
            _PENDING.update({"steps": None, "at": 0.0, "label": ""})
            return {"ok": False, "error": "There is nothing waiting for confirmation."}
        _PENDING.update({"steps": None, "at": 0.0, "label": ""})
    return run(steps, confirmed=True)


def run(steps: List[Dict[str, Any]], confirmed: bool = False, label: str = "") -> Dict[str, Any]:
    """Execute a workflow. Stops at the first destructive step unless confirmed."""
    if not isinstance(steps, list) or not steps:
        return {"ok": False, "error": "a workflow needs at least one step"}
    if len(steps) > MAX_STEPS:
        return {"ok": False, "error": "a workflow may have at most %d steps" % MAX_STEPS}

    gated = [s for s in steps if isinstance(s, dict) and needs_confirmation(s)]
    if gated and not confirmed:
        with _PENDING_LOCK:
            _PENDING.update({"steps": steps, "at": time.time(), "label": label})
        names = ", ".join(sorted({str(s.get("action") or "") for s in gated}))
        return {
            "ok": False,
            "needs_confirmation": True,
            "error": "This workflow includes irreversible steps: %s" % names,
            "message": "Say 'confirm' to run it, or 'cancel' to drop it.",
            "steps": [str(s.get("action") or s.get("tool") or "?") for s in gated],
        }

    started = time.time()
    results: List[Dict[str, Any]] = []

    def _prepared(step: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(step)
        if confirmed:
            out["_confirmed"] = True
        return out

    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            results.append({"ok": False, "_ok": False, "error": "step %d is not an object" % index})
            break
        if str(step.get("action") or "").lower() == "parallel" and isinstance(step.get("steps"), list):
            children = [_prepared(s) for s in step["steps"] if isinstance(s, dict)][:8]
            with ThreadPoolExecutor(max_workers=min(8, max(1, len(children)))) as pool:
                batch = list(pool.map(_run_one, children))
            results.extend(batch)
            if not all(b.get("_ok") for b in batch):
                break
            continue
        result = _run_one(_prepared(step))
        results.append(result)
        # An independent step can be flagged to continue after failure; the
        # default is stop, so a half-finished automation is never reported as done.
        if not result.get("_ok") and not step.get("continue_on_error"):
            break

    ok = bool(results) and all(r.get("_ok") for r in results)
    summary = summarise(results)
    logger.info("workflow %s: %s", "ok" if ok else "failed", summary)
    return {
        "ok": ok,
        "steps": results,
        "performed": len(results),
        "requested": len(steps),
        "elapsed_ms": int((time.time() - started) * 1000),
        "summary": summary,
    }


def summarise(results: List[Dict[str, Any]]) -> str:
    """One spoken line describing what actually happened."""
    if not results:
        return "I did not run anything, sir."
    done = [r for r in results if r.get("_ok")]
    failed = [r for r in results if not r.get("_ok")]
    parts = []
    if done:
        parts.append("%d step%s completed" % (len(done), "" if len(done) == 1 else "s"))
    if failed:
        reason = failed[0].get("error") or failed[0].get("message") or "it failed"
        parts.append("then %s stopped: %s" % (failed[0].get("step", "a step"), str(reason)[:140]))
    return (", ".join(parts) if parts else "Nothing ran") + "."
