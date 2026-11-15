"""Start / stop / inspect the floating bubble process.

The bubble is a separate GUI process (``pythonw -m jarvis.bubble``) so it keeps
running while the HUD tab is closed. This module is the only place that knows
how to launch it, and the daemon exposes it as ``/api/bubble`` so the HUD and
voice commands can turn it on and off.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import psutil

ROOT = Path(__file__).resolve().parent.parent
PID_PATH = Path.home() / ".jarvis" / "bubble.pid"
LOCK_PORT = 8799
LOG_PATH = Path(os.environ.get("JARVIS_LOG_DIR", str(Path.home() / ".jarvis"))) / "bubble.process.log"


def _python() -> str:
    """Prefer pythonw so a console window never flashes on screen."""
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")
    return str(windowless if windowless.exists() else exe)


def pid() -> Optional[int]:
    try:
        value = int(PID_PATH.read_text(encoding="utf-8").strip())
        process = psutil.Process(value)
        if process.is_running() and any("bubble" in part for part in process.cmdline()):
            return value
    except Exception:
        pass
    # Fallback: find any running jarvis.bubble process
    try:
        for p in psutil.process_iter(["pid", "cmdline"]):
            cmd = " ".join(p.info.get("cmdline") or [])
            if "jarvis.bubble" in cmd:
                PID_PATH.write_text(str(p.info["pid"]), encoding="utf-8")
                return p.info["pid"]
    except Exception:
        pass
    return None


def status() -> Dict[str, Any]:
    current = pid()
    return {"ok": True, "running": current is not None, "pid": current,
            "python": _python(), "lock_port": LOCK_PORT}


def start() -> Dict[str, Any]:
    current = pid()
    if current:
        return {**status(), "started": False, "message": "The bubble is already running."}

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = open(LOG_PATH, "ab", buffering=0)
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
    try:
        child = subprocess.Popen(
            [_python(), "-m", "jarvis.bubble"],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=handle,
            creationflags=flags,
        )
    except Exception as exc:
        handle.close()
        return {**status(), "started": False, "error": str(exc)}
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(child.pid), encoding="utf-8")
    return {**status(), "started": True, "pid": child.pid,
            "message": "The bubble is opening at the top of the screen."}


def stop() -> Dict[str, Any]:
    current = pid()
    if not current:
        try:
            PID_PATH.unlink()
        except Exception:
            pass
        return {**status(), "stopped": False, "message": "The bubble is not running."}
    try:
        process = psutil.Process(current)
        process.terminate()
        try:
            process.wait(timeout=3)
        except Exception:
            process.kill()
    except Exception as exc:
        return {**status(), "stopped": False, "error": str(exc)}
    try:
        PID_PATH.unlink()
    except Exception:
        pass
    try:
        from jarvis import settings

        settings.set("bubble_enabled", False)
    except Exception:
        pass
    return {"ok": True, "running": False, "pid": None, "stopped": True,
            "message": "The bubble is closed."}


def toggle() -> Dict[str, Any]:
    return stop() if pid() else start()


def ensure_started() -> Dict[str, Any]:
    return start()


__all__ = ["pid", "status", "start", "stop", "toggle", "ensure_started", "LOCK_PORT"]
