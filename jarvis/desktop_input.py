"""Real mouse and keyboard control for Windows, through SendInput.

Everything is ctypes + user32, so nothing extra has to be installed and the
assistant can drive any application the user can. Coordinates are physical
screen pixels; the process is marked per-monitor DPI aware on import so they
line up with UIA bounding rectangles and screenshots.
"""
from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger("jarvis.desktop_input")

user32 = ctypes.WinDLL("user32", use_last_error=True)

# --------------------------------------------------------------------------- DPI
def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor v2
        return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_dpi_awareness()

# --------------------------------------------------------------------------- structs
ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)  # unused, kept for clarity


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

WHEEL_DELTA = 120

VK = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D, "shift": 0x10,
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "pause": 0x13, "capslock": 0x14,
    "esc": 0x1B, "escape": 0x1B, "space": 0x20, "pageup": 0x21, "pgup": 0x21,
    "pagedown": 0x22, "pgdn": 0x22, "end": 0x23, "home": 0x24, "left": 0x25,
    "up": 0x26, "right": 0x27, "down": 0x28, "printscreen": 0x2C, "insert": 0x2D,
    "delete": 0x2E, "del": 0x2E, "win": 0x5B, "windows": 0x5B, "menu": 0x5D,
    "numlock": 0x90, "scrolllock": 0x91, "semicolon": 0xBA, "equals": 0xBB,
    "comma": 0xBC, "minus": 0xBD, "period": 0xBE, "slash": 0xBF,
    "backtick": 0xC0, "grave": 0xC0, "lbracket": 0xDB, "backslash": 0xDC,
    "rbracket": 0xDD, "quote": 0xDE,
}
for _i in range(1, 25):
    VK["f%d" % _i] = 0x6F + _i
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK[_c] = ord(_c.upper())
for _d in "0123456789":
    VK[_d] = ord(_d)

BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


def _send(*inputs: _INPUT) -> None:
    if not inputs:
        return
    array = (_INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), array, ctypes.sizeof(_INPUT))
    if sent != len(inputs):
        raise OSError("SendInput sent %d of %d events (error %d)" % (sent, len(inputs), ctypes.get_last_error()))


def _mouse_input(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> _INPUT:
    return _INPUT(type=INPUT_MOUSE, u=_INPUTUNION(mi=_MOUSEINPUT(dx, dy, data, flags, 0, None)))


def _key_input(vk: int = 0, scan: int = 0, flags: int = 0) -> _INPUT:
    return _INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=_KEYBDINPUT(vk, scan, flags, 0, None)))


# --------------------------------------------------------------------------- screen
def screen_metrics() -> Dict[str, int]:
    """Virtual desktop bounds in physical pixels (multi-monitor aware)."""
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
    SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
    return {
        "x": int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN)),
        "y": int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN)),
        "width": int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)),
        "height": int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)),
    }


def cursor_position() -> Dict[str, int]:
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return {"x": int(point.x), "y": int(point.y)}


def move_mouse(x: int, y: int, duration: float = 0.0) -> Dict[str, Any]:
    """Move the pointer. A small duration animates instead of teleporting."""
    start = cursor_position()
    x, y = int(x), int(y)
    if duration and duration > 0:
        steps = max(2, int(duration * 60))
        for i in range(1, steps + 1):
            t = i / steps
            user32.SetCursorPos(int(start["x"] + (x - start["x"]) * t), int(start["y"] + (y - start["y"]) * t))
            time.sleep(duration / steps)
    else:
        if not user32.SetCursorPos(x, y):
            raise OSError("SetCursorPos failed")
    return {"ok": True, "x": x, "y": y, "from": start}


def click(
    x: Optional[int] = None,
    y: Optional[int] = None,
    button: str = "left",
    double: bool = False,
    clicks: int = 1,
) -> Dict[str, Any]:
    """Click at a point (or wherever the pointer is) with any mouse button."""
    button = (button or "left").lower()
    if button not in BUTTONS:
        return {"ok": False, "error": "button must be left, right or middle"}
    if x is not None and y is not None:
        move_mouse(x, y)
        time.sleep(0.06)
    down, up = BUTTONS[button]
    total = max(1, int(clicks)) * (2 if double else 1)
    for _ in range(total):
        _send(_mouse_input(down), _mouse_input(up))
        time.sleep(0.05)
    pos = cursor_position()
    return {"ok": True, "button": button, "double": double, "clicks": total, "at": pos}


def scroll(amount: int = -3, horizontal: bool = False) -> Dict[str, Any]:
    """Scroll the wheel. Negative scrolls down, positive up (one unit = one notch)."""
    delta = int(-amount * WHEEL_DELTA)
    flag = MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL
    _send(_mouse_input(flag, data=delta & 0xFFFFFFFF))
    return {"ok": True, "notches": amount, "horizontal": horizontal}


def drag(x1: int, y1: int, x2: int, y2: int, button: str = "left", duration: float = 0.3) -> Dict[str, Any]:
    """Press, move and release - for sliders, selections and drag-and-drop."""
    down, up = BUTTONS[(button or "left").lower()]
    move_mouse(x1, y1)
    time.sleep(0.05)
    _send(_mouse_input(down))
    time.sleep(0.05)
    move_mouse(x2, y2, duration=duration)
    time.sleep(0.05)
    _send(_mouse_input(up))
    return {"ok": True, "from": {"x": x1, "y": y1}, "to": {"x": x2, "y": y2}}


# --------------------------------------------------------------------------- keyboard
def _vk_for(name: str) -> int:
    key = (name or "").strip().lower()
    if key in VK:
        return VK[key]
    if len(key) == 1:
        code = user32.VkKeyScanW(ctypes.c_wchar(key))
        if code != -1:
            return code & 0xFF
        if key.isalpha():
            return ord(key.upper())
    raise ValueError("unknown key %r" % name)


def type_text(text: str, interval: float = 0.0) -> Dict[str, Any]:
    """Type literal text into the focused control (Unicode, layout independent)."""
    data = str(text)
    events: List[_INPUT] = []
    for ch in data:
        for unit in ch.encode("utf-16-le").decode("utf-16-le"):
            scan = ord(unit)
            events.append(_key_input(scan=scan, flags=KEYEVENTF_UNICODE))
            events.append(_key_input(scan=scan, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    # SendInput caps out around a few hundred events reliably; chunk it.
    chunk = 200
    for i in range(0, len(events), chunk):
        _send(*events[i:i + chunk])
        if interval:
            time.sleep(interval * min(chunk, len(events) - i) / 2)
    return {"ok": True, "characters": len(data)}


def press(keys: str, repeat: int = 1) -> Dict[str, Any]:
    """Press a key or combination, e.g. ``"ctrl+s"``, ``"alt+tab"``, ``"enter"``."""
    parts = [p.strip() for p in str(keys or "").replace("-", "+").split("+") if p.strip()]
    if not parts:
        return {"ok": False, "error": "no key given"}
    try:
        codes = [_vk_for(p) for p in parts]
    except ValueError as exc:
        # Spoken input is untrusted: report the miss instead of raising into the caller.
        return {"ok": False, "keys": keys, "error": str(exc)}
    for _ in range(max(1, int(repeat))):
        for code in codes:
            _send(_key_input(vk=code))
            time.sleep(0.01)
        for code in reversed(codes):
            _send(_key_input(vk=code, flags=KEYEVENTF_KEYUP))
            time.sleep(0.01)
    return {"ok": True, "keys": keys, "repeat": repeat}


def hold(keys: Sequence[str], seconds: float = 0.5) -> Dict[str, Any]:
    codes = [_vk_for(k) for k in keys]
    for code in codes:
        _send(_key_input(vk=code))
    time.sleep(max(0.05, float(seconds)))
    for code in reversed(codes):
        _send(_key_input(vk=code, flags=KEYEVENTF_KEYUP))
    return {"ok": True, "keys": list(keys), "seconds": seconds}


# --------------------------------------------------------------------------- windows
def _window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def list_windows() -> List[Dict[str, Any]]:
    """Top-level windows with a title, in z-order."""
    out: List[Dict[str, Any]] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _window_title(hwnd)
        if not title:
            return True
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        out.append({
            "hwnd": int(hwnd),
            "title": title,
            "pid": int(pid.value),
            "rect": {"x": rect.left, "y": rect.top, "width": rect.right - rect.left, "height": rect.bottom - rect.top},
            "foreground": bool(hwnd == user32.GetForegroundWindow()),
        })
        return True

    user32.EnumWindows(enum_proc(_cb), 0)
    return out


def active_window() -> Dict[str, Any]:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return {"title": "", "hwnd": 0}
    info = [w for w in list_windows() if w["hwnd"] == int(hwnd)]
    if info:
        return info[0]
    title = _window_title(hwnd)
    if not title:
        # Some console hosts report an empty caption; the process name is a
        # more useful label for the assistant than nothing at all.
        try:
            import psutil

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            title = psutil.Process(pid.value).name()
        except Exception:
            title = ""
    return {"title": title, "hwnd": int(hwnd)}


def focus_window(title: str) -> Dict[str, Any]:
    """Bring the first window whose title contains ``title`` to the front."""
    needle = (title or "").strip().lower()
    if not needle:
        raise ValueError("a window title is required")
    matches = [w for w in list_windows() if needle in w["title"].lower()]
    if not matches:
        return {"ok": False, "error": "no window title contains %r" % title, "windows": [w["title"] for w in list_windows()][:20]}
    target = matches[0]
    hwnd = target["hwnd"]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    return {"ok": True, "title": target["title"], "hwnd": hwnd}


def _resolve_hwnd(title: Optional[str] = None) -> Tuple[Optional[int], str]:
    """Find hwnd by matching title, or return foreground window if title is empty or 'this'."""
    needle = (title or "").strip().lower()
    if not needle or needle in ("this", "the window", "this window", "active", "active window", "current"):
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            return int(hwnd), _window_title(hwnd) or "active window"
        return None, ""
    matches = [w for w in list_windows() if needle in w["title"].lower()]
    if matches:
        return matches[0]["hwnd"], matches[0]["title"]
    return None, ""


def maximize_window(title: Optional[str] = None) -> Dict[str, Any]:
    """Maximize the specified window or the active foreground window."""
    hwnd, name = _resolve_hwnd(title)
    if not hwnd:
        return {"ok": False, "error": ("no window matching %r" % title) if title else "no active window"}
    user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
    user32.SetForegroundWindow(hwnd)
    return {"ok": True, "title": name, "action": "maximize", "hwnd": hwnd, "message": "Maximized %s." % (name or "the window")}


def minimize_window(title: Optional[str] = None) -> Dict[str, Any]:
    """Minimize the specified window or the active foreground window."""
    needle = (title or "").strip().lower()
    if needle in ("all", "all windows", "everything", "desktop"):
        press("win+d")
        return {"ok": True, "title": "all windows", "action": "minimize_all", "message": "Minimized all windows."}
    hwnd, name = _resolve_hwnd(title)
    if not hwnd:
        return {"ok": False, "error": ("no window matching %r" % title) if title else "no active window"}
    user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
    return {"ok": True, "title": name, "action": "minimize", "hwnd": hwnd, "message": "Minimized %s." % (name or "the window")}


def restore_window(title: Optional[str] = None) -> Dict[str, Any]:
    """Restore a minimized or maximized window."""
    hwnd, name = _resolve_hwnd(title)
    if not hwnd:
        return {"ok": False, "error": ("no window matching %r" % title) if title else "no active window"}
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return {"ok": True, "title": name, "action": "restore", "hwnd": hwnd, "message": "Restored %s." % (name or "the window")}


def close_window(title: Optional[str] = None) -> Dict[str, Any]:
    """Close the specified window or the active foreground window gracefully."""
    hwnd, name = _resolve_hwnd(title)
    if not hwnd:
        return {"ok": False, "error": ("no window matching %r" % title) if title else "no active window"}
    user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
    return {"ok": True, "title": name, "action": "close", "hwnd": hwnd, "message": "Closed %s." % (name or "the window")}
