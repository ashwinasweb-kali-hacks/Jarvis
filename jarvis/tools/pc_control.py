"""Full host control for the JARVIS assistant.

One tool with many actions so the assistant can drive the whole desktop:
launch and close applications, browse the web, read/write/move/delete files,
search the disk, lock the machine, shut it down, restart it, take a screenshot,
control the volume, list and kill processes, and run a raw command.

Access is gated by three settings:

* ``pc_control_enabled`` (default on) - master switch for host automation.
* ``pc_full_access`` (default on) - when off, file actions are confined to the
  user's home directory and the project folder.
* ``pc_block_system_paths`` (default on) - when on, file *writes* and *deletes*
  under ``C:\\Windows`` and ``C:\\Program Files`` are refused (reads are fine).

Every execution is appended to ``~/.jarvis/actions.log`` by the tool registry,
so the trail of what the assistant did to the machine is always readable.
"""
from __future__ import annotations

import html
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvis.tools.base import Tool

logger = logging.getLogger("jarvis.tools.pc_control")

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Executable names for the applications people ask for by name.
KNOWN_APPS: Dict[str, List[str]] = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "calc": ["calc.exe"],
    "explorer": ["explorer.exe"],
    "files": ["explorer.exe"],
    "file explorer": ["explorer.exe"],
    "downloads": ["explorer.exe", str(Path.home() / "Downloads")],
    "documents": ["explorer.exe", str(Path.home() / "Documents")],
    "pictures": ["explorer.exe", str(Path.home() / "Pictures")],
    "terminal": ["wt.exe"],
    "cmd": ["cmd.exe"],
    "command prompt": ["cmd.exe"],
    "powershell": ["powershell.exe"],
    "task manager": ["taskmgr.exe"],
    "taskmgr": ["taskmgr.exe"],
    "paint": ["mspaint.exe"],
    "wordpad": ["write.exe"],
    "chrome": ["chrome.exe"],
    "google chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
    "microsoft edge": ["msedge.exe"],
    "firefox": ["firefox.exe"],
    "outlook": ["outlook.exe"],
    "discord": ["discord.exe"],
    "spotify": ["Spotify.exe"],
    "vscode": ["Code.exe"],
    "visual studio code": ["Code.exe"],
    "docker": ["Docker Desktop.exe"],
    "steam": ["steam.exe"],
    "control panel": ["control.exe"],
    "settings": ["ms-settings:"],
    "regedit": ["regedit.exe"],
    "snipping tool": ["SnippingTool.exe"],
    "camera": ["microsoft.windows.camera:"],
    "store": ["ms-windows-store:"],
    "task scheduler": ["taskschd.msc"],
    "services": ["services.msc"],
    "device manager": ["devmgmt.msc"],
    "windows terminal": ["wt.exe"],
    "excel": ["excel.exe"],
    "word": ["winword.exe"],
    "powerpoint": ["powerpnt.exe"],
}

SYSTEM_PROTECTED = (
    os.path.normcase(r"C:\Windows"),
    os.path.normcase(r"C:\Program Files"),
    os.path.normcase(r"C:\Program Files (x86)"),
)

_FILLER_PREFIXES = (
    "the file called ", "the file named ", "a file called ", "a file named ",
    "the folder called ", "the folder named ", "the file ", "the folder ",
    "the directory called ", "the directory named ", "the directory ",
    "file called ", "file named ", "folder called ", "folder named ",
    "called ", "named ",
)


def _setting(name: str, default: Any = None) -> Any:
    try:
        from jarvis import settings

        return settings.get(name, default)
    except Exception:
        return default


def _flag(name: str, default: bool = True) -> bool:
    value = _setting(name, default)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() not in ("0", "false", "no", "off", "disabled", "")


# Commands that can destroy data or take the machine down. They run only after
# an explicit yes (``confirm: true``) while ``confirm_destructive`` is on.
DANGEROUS_SHELL = re.compile(
    r"(?i)\b(format|diskpart|del\s+/[sq]|rmdir\s+/s|rd\s+/s|remove-item\s+-recurse|"
    r"remove-item\s+-force|reg\s+delete|bcdedit|cipher\s+/w|vssadmin\s+delete|"
    r"shutdown|stop-computer|restart-computer|set-mppreference|takeown|icacls\s+.*\/reset)\b"
)


def _confirmed(kw: Dict[str, Any]) -> bool:
    """Destructive actions need a real yes, not just the registry's default."""
    if not _flag("confirm_destructive", True):
        return True
    return kw.get("confirm") is True or str(kw.get("confirm", "")).strip().lower() in ("1", "true", "yes")


def control_enabled() -> bool:
    """True when the assistant is allowed to touch the host."""
    return _flag("pc_control_enabled", True)


def full_access() -> bool:
    """True when file actions may touch the whole disk."""
    return _flag("pc_full_access", True)


def _home_roots() -> List[Path]:
    roots = [Path.home()]
    try:
        roots.append(Path(os.environ.get("JARVIS_PROJECT_DIR", Path.cwd())).resolve())
    except Exception:
        pass
    out = []
    for r in roots:
        try:
            out.append(r.resolve())
        except Exception:
            continue
    return out


def resolve_path(raw: str, must_exist: bool = False) -> Path:
    """Resolve a user-supplied path, expanding ~ and relative segments."""
    text = str(raw or "").strip().strip('"').strip("'")
    if not text:
        raise ValueError("no path given")
    p = Path(os.path.expandvars(text)).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    else:
        p = p.resolve()

    if not full_access():
        allowed = False
        for root in _home_roots():
            try:
                p.relative_to(root)
                allowed = True
                break
            except ValueError:
                continue
        if not allowed:
            raise PermissionError(
                "Path '{0}' is outside the allowed roots. Enable pc_full_access for full disk access.".format(p)
            )

    if must_exist and not p.exists():
        raise FileNotFoundError("Path not found: {0}".format(p))
    return p


def _guard_writable(path: Path) -> None:
    """Refuse writes into Windows core directories unless the user opts in."""
    if not _flag("pc_block_system_paths", True):
        return
    norm = os.path.normcase(str(path))
    for blocked in SYSTEM_PROTECTED:
        if norm == blocked or norm.startswith(blocked + os.sep):
            raise PermissionError(
                "Refusing to modify '{0}': it is a protected system path "
                "(set pc_block_system_paths=0 to allow it).".format(path)
            )


def _installed(package: str) -> bool:
    """Did winget really install it? Verified, never assumed."""
    try:
        res = _run(["winget", "list", "--accept-source-agreements", "--disable-interactivity"], timeout=60)
        haystack = ((res.get("stdout") or "") + (res.get("stderr") or "")).lower()
        return package.lower() in haystack
    except Exception:
        return False


def run_powershell(command: str, timeout: int = 60) -> Dict[str, Any]:
    """Run a PowerShell command and return its real output.

    This is the escape hatch for anything the structured actions do not cover.
    It is deliberately non-interactive: a command that stops for input is killed
    at the timeout and reported as a failure instead of hanging the assistant.
    """
    text = str(command or "").strip()
    if not text:
        return {"ok": False, "error": "no command given"}
    started = time.time()
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", text],
            capture_output=True, text=True, timeout=max(5, int(timeout)),
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "command": text, "error": "timed out after {0}s".format(timeout)}
    except Exception as exc:
        return {"ok": False, "command": text, "error": str(exc)}
    return {
        "ok": proc.returncode == 0,
        "command": text,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-6000:],
        "stderr": (proc.stderr or "")[-2000:],
        "elapsed_ms": int((time.time() - started) * 1000),
    }


def _start(cmd: List[str]) -> Dict[str, Any]:
    subprocess.Popen(cmd, shell=False, cwd=str(Path.home()))
    return {"ok": True, "message": "Launched {0}.".format(cmd[0]), "command": cmd}


def _run(cmd: List[str], timeout: int = 20) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-4000:],
            "stderr": (proc.stderr or "")[-2000:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "command timed out after {0}s".format(timeout)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _strip_html(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


class PCControlTool(Tool):
    """One tool, every desktop action the assistant needs."""

    name = "pc_control"
    description = (
        "Full control of the host PC: launch/close apps, browse the web, read, "
        "write, move, copy and delete files, search the disk, list and kill "
        "processes, lock the screen, shut down or restart the machine, take a "
        "screenshot, adjust the volume, and run a raw command."
    )
    risk = "safe"
    schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "open_app", "close_app", "list_processes", "kill_process",
                    "open_url", "open_file", "read_file", "write_file",
                    "delete_file", "move_file", "copy_file", "list_dir",
                    "create_folder", "search_files", "lock_screen", "shutdown",
                    "restart", "cancel_shutdown", "screenshot", "volume",
                    "system_info", "web_fetch", "web_search", "run_command",
                    "clipboard",
                    # Mouse, keyboard and window control
                    "move_mouse", "click", "double_click", "right_click",
                    "scroll", "drag", "type_text", "press_key", "focus_window",
                    "list_windows", "maximize_window", "minimize_window",
                    "restore_window", "close_window",
                    # Screen awareness (local OCR + UI Automation)
                    "screen", "screen_click",
                    # Shells and package management
                    "run_powershell", "install_app", "uninstall_app",
                    "list_installed", "browser", "workflow", "empty_recycle_bin",
                    "send_email", "read_email", "calendar", "bubble",
                ],
                "description": "The host action to perform",
            },
            "target": {"type": "string", "description": "App name, URL, path or pattern"},
            "path": {"type": "string", "description": "File or directory path"},
            "destination": {"type": "string", "description": "Destination path"},
            "content": {"type": "string", "description": "Text content for write_file"},
            "mode": {"type": "string", "enum": ["write", "append"], "description": "Write mode"},
            "delay_seconds": {"type": "integer", "description": "Delay before shutdown/restart"},
            "limit": {"type": "integer", "description": "Max results"},
            "timeout": {"type": "integer", "description": "Command timeout in seconds"},
            "x": {"type": "integer", "description": "Screen X coordinate (physical pixels)"},
            "y": {"type": "integer", "description": "Screen Y coordinate (physical pixels)"},
            "x2": {"type": "integer", "description": "Drag end X"},
            "y2": {"type": "integer", "description": "Drag end Y"},
            "button": {"type": "string", "enum": ["left", "right", "middle"]},
            "double": {"type": "boolean", "description": "Double click"},
            "amount": {"type": "integer", "description": "Scroll notches; negative scrolls down"},
            "keys": {"type": "string", "description": "Key or combo, e.g. ctrl+s, alt+tab, enter"},
            "text": {"type": "string", "description": "Text to type or spoken command"},
            "command": {"type": "string", "description": "PowerShell command"},
            "package": {"type": "string", "description": "winget package id or name"},
            "confirm": {"type": "boolean", "description": "Explicit confirmation for destructive actions"},
            "steps": {"type": "array", "description": "Workflow steps for action=workflow"},
        },
        "required": ["action"],
    }

    # ------------------------------------------------------------------ run
    def run(self, **kwargs: Any) -> Dict[str, Any]:
        action = str(kwargs.get("action", "")).strip().lower()
        target = str(kwargs.get("target", "") or "").strip()
        path = str(kwargs.get("path", "") or "").strip()
        destination = str(kwargs.get("destination", "") or "").strip()
        content = kwargs.get("content", "")
        mode = str(kwargs.get("mode", "write") or "write").lower()
        limit = int(kwargs.get("limit", 50) or 50)
        timeout = int(kwargs.get("timeout", 30) or 30)

        if not control_enabled():
            return {"ok": False, "status": "blocked", "message": "PC control is switched off (pc_control_enabled)."}

        handler = getattr(self, "_a_" + action, None)
        if handler is None:
            return {"ok": False, "error": "Unknown PC action: {0}".format(action)}
        try:
            # Every handler receives the normalised keys plus whatever else the
            # caller sent (x/y, keys, text, package, confirm, steps...), so new
            # actions do not have to be added to this signature too.
            call_args: Dict[str, Any] = {
                "target": target, "path": path, "destination": destination,
                "content": content, "mode": mode, "limit": limit, "timeout": timeout,
                "delay_seconds": int(kwargs.get("delay_seconds", 0) or 0),
            }
            for key, value in kwargs.items():
                call_args.setdefault(key, value)
            result = handler(**call_args)
            if isinstance(result, dict):
                result.setdefault("action", action)
            return result
        except PermissionError as exc:
            return {"ok": False, "status": "blocked", "action": action, "error": str(exc)}
        except Exception as exc:
            logger.exception("pc_control %s failed", action)
            return {"ok": False, "action": action, "error": str(exc)}

    # --------------------------------------------------------------- apps
    def _a_open_app(self, **kw: Any) -> Dict[str, Any]:
        target = kw["target"]
        if not target:
            return {"ok": False, "error": "no application named"}
        clean = target.strip().strip('"').strip("'")
        for key, cmd in KNOWN_APPS.items():
            if clean.lower() == key or clean.lower().startswith(key + " "):
                if key in ("downloads", "documents", "pictures"):
                    return _start([cmd[0], cmd[1]])
                if cmd[0].endswith(":"):  # ms-settings: style URI
                    return _start(["cmd.exe", "/c", "start", "", cmd[0]])
                return _start(cmd)
        # Unknown app: let Windows resolve it.
        return _start(["cmd.exe", "/c", "start", "", clean])

    def _a_close_app(self, **kw: Any) -> Dict[str, Any]:
        target = kw["target"].strip()
        if not target:
            return {"ok": False, "error": "no application named"}
        name = target if target.lower().endswith(".exe") else target + ".exe"
        res = _run(["taskkill", "/IM", name, "/F"], timeout=15)
        if not res.get("ok"):
            # Fall back to killing by window title fragment.
            res2 = _run(["taskkill", "/FI", "WINDOWTITLE eq {0}*".format(target), "/F"], timeout=15)
            if not res2.get("ok"):
                return {"ok": False, "error": res.get("stderr") or "could not close {0}".format(target),
                        "detail": res2.get("stdout")}
        return {"ok": True, "message": "Closed {0}.".format(target)}

    def _a_list_processes(self, **kw: Any) -> Dict[str, Any]:
        try:
            import psutil  # type: ignore
        except ImportError:
            return {"ok": False, "error": "psutil not installed"}
        rows = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                info = p.info
                rows.append({
                    "pid": info.get("pid"),
                    "name": info.get("name"),
                    "memory_mb": round((info.get("memory_info") or {}).rss / 1024 / 1024, 1)
                    if info.get("memory_info") else None,
                })
            except Exception:
                continue
        rows.sort(key=lambda r: r.get("memory_mb") or 0, reverse=True)
        return {"ok": True, "count": len(rows), "processes": rows[:int(kw.get("limit") or 50)]}

    def _a_kill_process(self, **kw: Any) -> Dict[str, Any]:
        target = kw["target"].strip()
        if not target:
            return {"ok": False, "error": "no process named"}
        if target.isdigit():
            res = _run(["taskkill", "/PID", target, "/F"], timeout=15)
        else:
            name = target if target.lower().endswith(".exe") else target + ".exe"
            res = _run(["taskkill", "/IM", name, "/F"], timeout=15)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("stderr") or "could not kill {0}".format(target)}
        return {"ok": True, "message": "Killed {0}.".format(target)}

    # ---------------------------------------------------------------- web
    def _a_open_url(self, **kw: Any) -> Dict[str, Any]:
        target = kw["target"].strip()
        if not target:
            return {"ok": False, "error": "no address given"}
        if target.lower().startswith(("search:", "google:", "find:")):
            query = target.split(":", 1)[1].strip()
            url = "https://duckduckgo.com/?q=" + urllib.parse.quote(query)
        elif re.match(r"^[\w-]+(\.[\w-]+)+(/.*)?$", target):
            url = "https://" + target
        elif " " in target and "." not in target:
            url = "https://duckduckgo.com/?q=" + urllib.parse.quote(target)
        else:
            url = target if target.lower().startswith("http") else "https://" + target
        subprocess.Popen(["cmd.exe", "/c", "start", "", url], shell=False)
        return {"ok": True, "message": "Opened {0} in the browser.".format(url), "url": url}

    def _a_web_fetch(self, **kw: Any) -> Dict[str, Any]:
        url = kw["target"].strip()
        if not url:
            return {"ok": False, "error": "no address given"}
        if not url.lower().startswith("http"):
            url = "https://" + url
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Accept": "text/html"})
        try:
            with urllib.request.urlopen(req, timeout=kw.get("timeout") or 30) as resp:
                raw = resp.read(600000).decode("utf-8", "replace")
        except Exception as exc:
            return {"ok": False, "error": "could not read {0}: {1}".format(url, exc)}
        text = _strip_html(raw)
        max_chars = int(kw.get("limit") or 6000)
        return {
            "ok": True,
            "url": url,
            "title": (re.search(r"(?is)<title[^>]*>(.*?)</title>", raw) or [None, ""])[1].strip()[:200],
            "text": text[:max_chars],
            "chars": len(text),
        }

    def _a_web_search(self, **kw: Any) -> Dict[str, Any]:
        query = str(kw.get("target") or kw.get("query") or "").strip()
        if not query:
            return {"ok": False, "error": "no query given"}
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        req = urllib.request.Request(
            "https://lite.duckduckgo.com/lite/",
            data=data,
            headers={"User-Agent": BROWSER_UA, "Referer": "https://lite.duckduckgo.com/"},
        )
        try:
            with urllib.request.urlopen(req, timeout=kw.get("timeout") or 15) as resp:
                raw = resp.read(400000).decode("utf-8", "replace")
        except Exception as exc:
            return {"ok": False, "error": "search failed: {0}".format(exc)}
        results = []
        links = re.findall(r'<a\s+[^>]*href=[\'"]([^\'"]+)[\'"][^>]*class=[\'"]result-link[\'"][^>]*>(.*?)</a>', raw, re.DOTALL)
        snippets = re.findall(r'<td[^>]+class=[\'"]result-snippet[\'"][^>]*>(.*?)</td>', raw, re.DOTALL)
        for i, (href, title_html) in enumerate(links):
            title = _strip_html(title_html)
            snip = _strip_html(snippets[i]) if i < len(snippets) else ""
            if href.startswith("//duckduckgo.com/l/?uddg="):
                href = urllib.parse.unquote(href.split("uddg=", 1)[1].split("&", 1)[0])
            if title:
                results.append({"title": title[:160], "url": href, "snippet": snip})
            if len(results) >= int(kw.get("limit") or 8):
                break
        return {"ok": True, "query": query, "count": len(results), "results": results}

    # -------------------------------------------------------------- files
    def _a_read_file(self, **kw: Any) -> Dict[str, Any]:
        p = resolve_path(kw["path"], must_exist=True)
        if not p.is_file():
            return {"ok": False, "error": "not a file: {0}".format(p)}
        max_bytes = int(kw.get("limit") or 65536)
        data = p.read_bytes()[:max_bytes]
        return {
            "ok": True,
            "path": str(p),
            "bytes": len(data),
            "content": data.decode("utf-8", "replace"),
        }

    def _a_write_file(self, **kw: Any) -> Dict[str, Any]:
        p = resolve_path(kw["path"])
        _guard_writable(p)
        content = kw.get("content") or ""
        mode = kw.get("mode", "write")
        p.parent.mkdir(parents=True, exist_ok=True)
        if mode == "append":
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(str(content))
        else:
            p.write_text(str(content), encoding="utf-8")
        return {
            "ok": True,
            "path": str(p),
            "mode": mode,
            "bytes": len(str(content).encode("utf-8")),
            "message": "Wrote {0} bytes to {1}.".format(len(str(content).encode("utf-8")), p),
        }

    def _a_delete_file(self, **kw: Any) -> Dict[str, Any]:
        if not _confirmed(kw):
            return {
                "ok": False,
                "needs_confirmation": True,
                "error": "Deleting '{0}' cannot be undone. Ask the user to confirm first.".format(kw.get("path") or kw.get("target")),
            }
        p = resolve_path(kw["path"] or kw.get("target") or "", must_exist=True)
        _guard_writable(p)
        if p.is_dir():
            shutil.rmtree(p)
            return {"ok": True, "path": str(p), "message": "Deleted folder {0}.".format(p)}
        p.unlink()
        return {"ok": True, "path": str(p), "message": "Deleted {0}.".format(p)}

    def _a_move_file(self, **kw: Any) -> Dict[str, Any]:
        src = resolve_path(kw["path"], must_exist=True)
        dst = resolve_path(kw["destination"])
        _guard_writable(src)
        _guard_writable(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"ok": True, "source": str(src), "destination": str(dst),
                "message": "Moved {0} to {1}.".format(src, dst)}

    def _a_copy_file(self, **kw: Any) -> Dict[str, Any]:
        src = resolve_path(kw["path"], must_exist=True)
        dst = resolve_path(kw["destination"])
        _guard_writable(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
        else:
            shutil.copy2(str(src), str(dst))
        return {"ok": True, "source": str(src), "destination": str(dst),
                "message": "Copied {0} to {1}.".format(src, dst)}

    def _a_list_dir(self, **kw: Any) -> Dict[str, Any]:
        raw = kw["path"] or str(Path.home())
        p = resolve_path(raw, must_exist=True)
        if not p.is_dir():
            return {"ok": False, "error": "not a folder: {0}".format(p)}
        entries = []
        for child in sorted(p.iterdir(), key=lambda c: c.name.lower()):
            try:
                entries.append({
                    "name": child.name,
                    "type": "dir" if child.is_dir() else "file",
                    "size": child.stat().st_size if child.is_file() else None,
                })
            except OSError:
                continue
            if len(entries) >= int(kw.get("limit") or 200):
                break
        return {"ok": True, "path": str(p), "count": len(entries), "entries": entries}

    def _a_create_folder(self, **kw: Any) -> Dict[str, Any]:
        p = resolve_path(kw["path"])
        _guard_writable(p)
        p.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "path": str(p), "message": "Created folder {0}.".format(p)}

    def _a_search_files(self, **kw: Any) -> Dict[str, Any]:
        pattern = kw["target"].strip()
        if not pattern:
            return {"ok": False, "error": "no search pattern given"}
        root = resolve_path(kw["path"] or str(Path.home()), must_exist=True)
        if not root.is_dir():
            return {"ok": False, "error": "not a folder: {0}".format(root)}
        matches = []
        limit = int(kw.get("limit") or 50)
        needle = pattern.lower()
        try:
            for dirpath, _dirs, files in os.walk(str(root)):
                for name in files:
                    if needle in name.lower():
                        full = os.path.join(dirpath, name)
                        try:
                            size = os.path.getsize(full)
                        except OSError:
                            size = None
                        matches.append({"path": full, "name": name, "size": size})
                        if len(matches) >= limit:
                            break
                if len(matches) >= limit:
                    break
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "root": str(root), "pattern": pattern,
                "count": len(matches), "matches": matches}

    def _a_open_file(self, **kw: Any) -> Dict[str, Any]:
        p = resolve_path(kw["path"], must_exist=True)
        try:
            os.startfile(str(p))  # type: ignore[attr-defined]
        except AttributeError:
            subprocess.Popen(["cmd.exe", "/c", "start", "", str(p)], shell=False)
        return {"ok": True, "path": str(p), "message": "Opened {0}.".format(p)}

    # -------------------------------------------------------------- power
    def _a_lock_screen(self, **kw: Any) -> Dict[str, Any]:
        subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
        return {"ok": True, "message": "Workstation locked."}

    def _a_shutdown(self, **kw: Any) -> Dict[str, Any]:
        delay = max(0, int(kw.get("delay_seconds", 5) or 0))
        res = _run(["shutdown", "/s", "/t", str(delay), "/c", "JARVIS is shutting down the PC"], timeout=15)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("stderr") or res.get("error") or "shutdown failed"}
        return {"ok": True, "delay": delay, "message": "The PC will shut down in {0} seconds.".format(delay)}

    def _a_restart(self, **kw: Any) -> Dict[str, Any]:
        delay = max(0, int(kw.get("delay_seconds", 5) or 0))
        res = _run(["shutdown", "/r", "/t", str(delay), "/c", "JARVIS is restarting the PC"], timeout=15)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("stderr") or res.get("error") or "restart failed"}
        return {"ok": True, "delay": delay, "message": "The PC will restart in {0} seconds.".format(delay)}

    def _a_cancel_shutdown(self, **kw: Any) -> Dict[str, Any]:
        res = _run(["shutdown", "/a"], timeout=10)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("stderr") or "no shutdown to cancel"}
        return {"ok": True, "message": "Pending shutdown cancelled."}

    # --------------------------------------------------------------- misc
    def _a_screenshot(self, **kw: Any) -> Dict[str, Any]:
        shot = Path.home() / "Pictures" / "jarvis_screenshot.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        script = (
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
            "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
            "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height; "
            "$g=[System.Drawing.Graphics]::FromImage($bmp); "
            "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size); "
            "$bmp.Save('{0}'); $g.Dispose(); $bmp.Dispose()".format(str(shot).replace("'", "''"))
        )
        res = _run(["powershell", "-NoProfile", "-Command", script], timeout=25)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("stderr") or "screenshot failed"}
        return {"ok": True, "path": str(shot), "message": "Screenshot saved to {0}.".format(shot)}

    def _a_volume(self, **kw: Any) -> Dict[str, Any]:
        action = (kw.get("target") or "").strip().lower()
        keys = {
            "volume_up": 0xAF, "up": 0xAF,
            "volume_down": 0xAE, "down": 0xAE,
            "mute": 0xAD, "unmute": 0xAD,
        }
        code = keys.get(action)
        if code is None:
            return {"ok": False, "error": "volume action must be volume_up, volume_down or mute"}
        script = "$wscript = New-Object -ComObject Wscript.Shell; $wscript.SendKeys([char]{0})".format(code)
        _run(["powershell", "-NoProfile", "-Command", script], timeout=10)
        return {"ok": True, "message": "Volume: {0}.".format(action)}

    def _a_system_info(self, **kw: Any) -> Dict[str, Any]:
        info = {
            "os": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "cpu_cores": os.cpu_count(),
            "hostname": platform.node(),
            "user": os.environ.get("USERNAME", ""),
            "uptime_seconds": int(time.time() - psutil_boot_time()) if True else None,
        }
        try:
            import psutil  # type: ignore

            info["ram_percent"] = psutil.virtual_memory().percent
            info["ram_total_mb"] = round(psutil.virtual_memory().total / 1024 / 1024)
            info["cpu_percent"] = psutil.cpu_percent(interval=0.1)
            info["battery"] = psutil.sensors_battery().percent if hasattr(psutil, "sensors_battery") else None
        except Exception:
            pass
        usage = shutil.disk_usage(str(Path.home()))
        info["disk_total_gb"] = round(usage.total / (1024 ** 3), 1)
        info["disk_used_gb"] = round(usage.used / (1024 ** 3), 1)
        info["disk_percent"] = round(usage.used / usage.total * 100, 1)
        return {"ok": True, "info": info}

    def _a_run_command(self, **kw: Any) -> Dict[str, Any]:
        command = kw.get("target") or kw.get("path") or ""
        if not command:
            return {"ok": False, "error": "no command given"}
        timeout = int(kw.get("timeout") or 60)
        try:
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=timeout,
                encoding="utf-8", errors="replace",
            )
            return {
                "ok": proc.returncode == 0,
                "command": command,
                "returncode": proc.returncode,
                "stdout": (proc.stdout or "")[-4000:],
                "stderr": (proc.stderr or "")[-2000:],
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "command timed out after {0}s".format(timeout)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------- mouse & keyboard
    def _a_move_mouse(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import desktop_input

        return desktop_input.move_mouse(int(kw.get("x") or 0), int(kw.get("y") or 0),
                                        float(kw.get("duration") or 0))

    def _a_click(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import desktop_input

        x, y = kw.get("x"), kw.get("y")
        return desktop_input.click(
            None if x is None or x == "" else int(x),
            None if y is None or y == "" else int(y),
            button=str(kw.get("button") or "left"),
            double=bool(kw.get("double")),
            clicks=int(kw.get("clicks") or 1),
        )

    def _a_double_click(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import desktop_input

        x, y = kw.get("x"), kw.get("y")
        return desktop_input.click(
            None if x is None or x == "" else int(x),
            None if y is None or y == "" else int(y),
            button=str(kw.get("button") or "left"),
            double=True,
        )

    def _a_right_click(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import desktop_input

        x, y = kw.get("x"), kw.get("y")
        return desktop_input.click(
            None if x is None or x == "" else int(x),
            None if y is None or y == "" else int(y),
            button="right",
        )

    def _a_scroll(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import desktop_input

        return desktop_input.scroll(int(kw.get("amount") or -3), bool(kw.get("horizontal")))

    def _a_drag(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import desktop_input

        return desktop_input.drag(
            int(kw.get("x") or 0), int(kw.get("y") or 0),
            int(kw.get("x2") or 0), int(kw.get("y2") or 0),
            button=str(kw.get("button") or "left"),
        )

    def _a_type_text(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import desktop_input

        text = str(kw.get("text") or kw.get("content") or kw.get("target") or "")
        if not text:
            return {"ok": False, "error": "nothing to type"}
        out = desktop_input.type_text(text)
        return {**out, "message": "Typed {0} characters.".format(len(text))}

    def _a_press_key(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import desktop_input

        keys = str(kw.get("keys") or kw.get("target") or "").strip()
        if not keys:
            return {"ok": False, "error": "no key given"}
        out = desktop_input.press(keys, repeat=int(kw.get("repeat") or 1))
        return {**out, "message": "Pressed {0}.".format(keys)}

    def _a_focus_window(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import desktop_input

        out = desktop_input.focus_window(str(kw.get("target") or ""))
        if out.get("ok"):
            out["message"] = "Focused {0}.".format(out.get("title"))
        return out

    def _a_list_windows(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import desktop_input

        wins = desktop_input.list_windows()
        return {"ok": True, "count": len(wins), "windows": wins[: int(kw.get("limit") or 25)],
                "message": "There are {0} open windows.".format(len(wins))}

    def _a_maximize_window(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import desktop_input

        return desktop_input.maximize_window(kw.get("target") or kw.get("title"))

    def _a_minimize_window(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import desktop_input

        return desktop_input.minimize_window(kw.get("target") or kw.get("title"))

    def _a_restore_window(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import desktop_input

        return desktop_input.restore_window(kw.get("target") or kw.get("title"))

    def _a_close_window(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import desktop_input

        return desktop_input.close_window(kw.get("target") or kw.get("title"))

    # -------------------------------------------------------- screen reading
    def _a_screen(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import screen

        mode = str(kw.get("target") or "describe").strip().lower()
        data = screen.snapshot(with_ocr=True)
        if mode.startswith("find"):
            name = mode[5:].strip(" :") or str(kw.get("text") or "")
            found = screen.find(name, data)
            return {"ok": bool(found), "element": found,
                    "message": ("Found {0}." if found else "I cannot see {0}.").format(name)}
        if mode in ("read", "text", "ocr"):
            return {"ok": True, "window": data.get("window"), "text": (data.get("text") or "")[:4000],
                    "elements": data.get("elements", [])[:60],
                    "message": "Read {0} characters from {1}.".format(
                        len(data.get("text") or ""), (data.get("window") or {}).get("title", "the screen"))}
        return {"ok": True, "spoken": screen.describe(data), "window": data.get("window"),
                "element_count": data.get("element_count"), "text": (data.get("text") or "")[:1500],
                "message": screen.describe(data)}

    def _a_screen_click(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import screen

        name = str(kw.get("target") or kw.get("text") or "").strip()
        if not name:
            return {"ok": False, "error": "what should I click?"}
        out = screen.click_element(name, double=bool(kw.get("double")))
        if out.get("ok"):
            out["message"] = "Clicked {0}.".format(out.get("name"))
        return out

    # ---------------------------------------------------------------- shells
    def _a_run_powershell(self, **kw: Any) -> Dict[str, Any]:
        command = str(kw.get("command") or kw.get("target") or kw.get("text") or "").strip()
        if not command:
            return {"ok": False, "error": "no PowerShell command given"}
        if DANGEROUS_SHELL.search(command) and not _confirmed(kw):
            return {"ok": False, "needs_confirmation": True,
                    "error": "That PowerShell command can be destructive. Confirm before I run it."}
        return run_powershell(command, timeout=int(kw.get("timeout") or 60))

    # ------------------------------------------------------- package manager
    def _a_install_app(self, **kw: Any) -> Dict[str, Any]:
        package = str(kw.get("package") or kw.get("target") or "").strip()
        if not package:
            return {"ok": False, "error": "which package should I install?"}
        if not shutil.which("winget"):
            return {"ok": False, "error": "winget is not available on this machine"}
        args = ["winget", "install", "--silent", "--accept-package-agreements",
                "--accept-source-agreements", "--disable-interactivity"]
        # winget ids contain dots and no spaces (e.g. 7zip.7zip); names are free text.
        if " " in package or "." not in package:
            args += ["--name", package]
        else:
            args += ["--id", package, "--exact"]
        location = str(kw.get("location") or "").strip()
        if location:
            args += ["--location", location]
        res = _run(args, timeout=int(kw.get("timeout") or 420))
        out = (res.get("stdout") or "") + (res.get("stderr") or "")
        ok = res.get("ok") or "Successfully installed" in out
        if not ok:
            return {"ok": False, "error": "winget could not install {0}".format(package),
                    "output": out[-1500:]}
        return {"ok": True, "package": package,
                "verified": _installed(package),
                "message": "Installed {0}.".format(package)}

    def _a_uninstall_app(self, **kw: Any) -> Dict[str, Any]:
        package = str(kw.get("package") or kw.get("target") or "").strip()
        if not package:
            return {"ok": False, "error": "which package should I uninstall?"}
        if not _confirmed(kw):
            return {"ok": False, "needs_confirmation": True,
                    "error": "Uninstalling {0} cannot be undone. Confirm first.".format(package)}
        if not shutil.which("winget"):
            return {"ok": False, "error": "winget is not available on this machine"}
        args = ["winget", "uninstall", "--silent", "--disable-interactivity"]
        args += (["--name", package] if " " in package or "." not in package else ["--id", package, "--exact"])
        res = _run(args, timeout=int(kw.get("timeout") or 300))
        out = (res.get("stdout") or "") + (res.get("stderr") or "")
        ok = res.get("ok") or "Successfully uninstalled" in out
        return {"ok": ok, "package": package, "output": out[-1200:],
                "message": ("Uninstalled {0}.".format(package) if ok else "Could not uninstall {0}.".format(package))}

    def _a_list_installed(self, **kw: Any) -> Dict[str, Any]:
        if not shutil.which("winget"):
            return {"ok": False, "error": "winget is not available on this machine"}
        res = _run(["winget", "list", "--accept-source-agreements", "--disable-interactivity"],
                   timeout=int(kw.get("timeout") or 60))
        lines = [l.strip() for l in (res.get("stdout") or "").splitlines() if l.strip()]
        limit = int(kw.get("limit") or 40)
        return {"ok": bool(res.get("ok")), "count": max(0, len(lines) - 3),
                "apps": lines[2: 2 + limit], "message": "Listed installed applications."}

    # ----------------------------------------------------- browser and flows
    def _a_browser(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import browser

        action = str(kw.get("browser_action") or kw.get("target") or "status").strip().lower()
        args = {k: v for k, v in kw.items() if k not in ("action", "tool")}
        out = browser.run(action, **args)
        out.setdefault("message", out.get("error") or ("Browser: {0}".format(action)))
        return out

    def _a_workflow(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import workflow

        steps = kw.get("steps")
        if isinstance(steps, str):
            try:
                steps = json.loads(steps)
            except Exception as exc:
                return {"ok": False, "error": "steps is not valid JSON: {0}".format(exc)}
        if not isinstance(steps, list) or not steps:
            return {"ok": False, "error": "a workflow needs a list of steps"}
        out = workflow.run(steps, confirmed=bool(kw.get("confirm")))
        out.setdefault("message", out.get("summary") or out.get("error") or "Workflow finished.")
        return out

    # ------------------------------------------------------ mail & calendar
    def _a_send_email(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import mailbox

        to = str(kw.get("to") or kw.get("target") or "").strip()
        subject = str(kw.get("subject") or "").strip() or "Message from JARVIS"
        body = str(kw.get("body") or kw.get("content") or kw.get("text") or "").strip()
        return mailbox.send(to, subject, body)

    def _a_read_email(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import mailbox

        return mailbox.unread(limit=int(kw.get("limit") or 5))

    def _a_calendar(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import mailbox

        return mailbox.calendar(days=int(kw.get("days") or 1))

    def _a_bubble(self, **kw: Any) -> Dict[str, Any]:
        from jarvis import bubblectl

        target = str(kw.get("target") or kw.get("action") or "toggle").strip().lower()
        if target in ("open", "show", "start", "on"):
            return bubblectl.start()
        elif target in ("close", "hide", "stop", "off"):
            return bubblectl.stop()
        elif target in ("status", "check"):
            return bubblectl.status()
        return bubblectl.toggle()

    def _a_empty_recycle_bin(self, **kw: Any) -> Dict[str, Any]:
        if not _confirmed(kw):
            return {"ok": False, "needs_confirmation": True,
                    "error": "Emptying the recycle bin cannot be undone. Confirm first."}
        return run_powershell("Clear-RecycleBin -Force -ErrorAction SilentlyContinue", timeout=120)

    def _a_clipboard(self, **kw: Any) -> Dict[str, Any]:
        action = (kw.get("target") or "get").strip().lower()
        try:
            import win32clipboard  # type: ignore

            if action == "set":
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(str(kw.get("content") or ""))
                win32clipboard.CloseClipboard()
                return {"ok": True, "message": "Clipboard updated."}
            win32clipboard.OpenClipboard()
            text = win32clipboard.GetClipboardData()
            win32clipboard.CloseClipboard()
            return {"ok": True, "clipboard": text}
        except Exception as exc:
            return {"ok": False, "error": "clipboard unavailable: {0}".format(exc)}


def psutil_boot_time() -> float:
    try:
        import psutil  # type: ignore

        return psutil.boot_time()
    except Exception:
        return time.time()


__all__ = ["PCControlTool", "control_enabled", "full_access", "resolve_path", "KNOWN_APPS"]
