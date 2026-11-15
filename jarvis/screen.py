"""Screen awareness: what is on the display, without throwing pixels at a model.

Two local senses are tried in order, both free and offline:

1. **Windows UI Automation** - the accessibility tree of the focused window:
   buttons, menus, text fields, list items, with exact coordinates. This is what
   the assistant uses to *understand* and *click* things.
2. **Windows OCR** - ``Windows.Media.Ocr`` reads the pixels for anything the
   automation tree does not describe (canvas apps, images, games, PDFs).

A cloud vision model is only consulted on explicit request
(:func:`describe_with_vision`), never on a timer, so screen understanding costs
nothing and does not burn Gemini quota.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.screen")

_TMP = Path(os.environ.get("JARVIS_TMP_DIR", r"E:\JARVIS\tmp"))
_CACHE_DIR = _TMP / "screen"

# Last snapshot, so a follow-up "click the second one" does not re-read UIA.
_last_snapshot: Dict[str, Any] = {"at": 0.0, "data": None}

MAX_ELEMENTS = 400


# --------------------------------------------------------------------------- image
def _grab(bbox: Optional[Tuple[int, int, int, int]] = None):
    from PIL import ImageGrab

    return ImageGrab.grab(bbox=bbox, all_screens=True)


def screenshot(path: Optional[str] = None, window_only: bool = True) -> Dict[str, Any]:
    """Capture the focused window (or the whole desktop) to a PNG on E:."""
    rect = None
    win = None
    if window_only:
        try:
            from jarvis import desktop_input

            win = desktop_input.active_window()
            for item in desktop_input.list_windows():
                if item["hwnd"] == win.get("hwnd"):
                    r = item["rect"]
                    rect = (r["x"], r["y"], r["x"] + r["width"], r["y"] + r["height"])
                    break
        except Exception:
            rect = None

    if rect is None or rect[2] - rect[0] < 32 or rect[3] - rect[1] < 32:
        rect = None
        window_only = False

    image = _grab(rect)
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = Path(path) if path else _CACHE_DIR / ("screen-%d.png" % int(time.time() * 1000))
    if target.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        target = target.with_suffix(".png")
    image.save(target)
    return {
        "ok": True,
        "path": str(target),
        "width": image.width,
        "height": image.height,
        "window_only": window_only,
        "bbox": list(rect) if rect else None,
        "window": win,
    }


def screenshot_bytes() -> bytes:
    """The focused window as JPEG bytes, for the vision fallback."""
    shot = screenshot()
    from PIL import Image

    image = Image.open(shot["path"])
    if max(image.size) > 1600:
        image.thumbnail((1600, 1600))
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=82)
    return buf.getvalue()


# --------------------------------------------------------------------------- UIA
def _uia_ready() -> bool:
    try:
        import pywinauto  # noqa: F401

        return True
    except Exception:
        return False


def _uia_budget() -> float:
    """How long the UI Automation walk may take before we speak what we have.

    WhatsApp and other Electron apps expose enormous trees, and a full
    ``descendants()`` walk can take 10 s - far too slow for a spoken answer.
    """
    try:
        from jarvis import settings

        return max(0.5, float(settings.get("screen_uia_budget", 2.5) or 2.5))
    except Exception:
        return 2.5


def _element_from(info: Any) -> Optional[Dict[str, Any]]:
    name = (info.name or "").strip()
    ctype = (info.control_type or "").strip()
    if not ctype or (not name and ctype not in ("Edit", "Document")):
        return None
    rect = info.rectangle
    return {
        "name": name,
        "type": ctype,
        "automation_id": getattr(info, "automation_id", "") or "",
        "enabled": bool(getattr(info, "enabled", True)),
        "x": int(rect.left),
        "y": int(rect.top),
        "width": int(rect.width()),
        "height": int(rect.height()),
        "center": [int((rect.left + rect.right) / 2), int((rect.top + rect.bottom) / 2)],
    }


def _collect_elements(
    handle: Optional[int] = None,
    max_elements: int = MAX_ELEMENTS,
    budget: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Walk the automation tree of one window into flat, speech-friendly dicts.

    The walk is breadth-first with a deadline: top-level controls (the ones a
    person would name) are collected first, and a pathological app can never
    stall the assistant. Whatever was collected when the budget runs out is
    returned - partial knowledge beats a ten-second silence.
    """
    from pywinauto import Desktop

    desktop = Desktop(backend="uia")
    if handle:
        wrapper = desktop.window(handle=handle)
    else:
        try:
            wrapper = desktop.window(handle=desktop.get_active_window_handle())
        except Exception:
            wrapper = None
    if wrapper is None:
        return []

    deadline = time.time() + (budget if budget is not None else _uia_budget())
    found: List[Dict[str, Any]] = []
    queue: List[Any] = [wrapper]
    visited = 0

    while queue and len(found) < max_elements and time.time() < deadline:
        node = queue.pop(0)
        try:
            children = node.children()
        except Exception:
            continue
        for child in children:
            if time.time() >= deadline:
                break
            visited += 1
            try:
                item = _element_from(child.element_info)
            except Exception:
                item = None
            if item:
                found.append(item)
                if len(found) >= max_elements:
                    break
            queue.append(child)
            if visited >= max_elements * 8:
                break
    return found


def _ocr(image_path: str) -> Dict[str, Any]:
    """Read text with the Windows OCR engine that ships with the OS."""
    async def _run() -> Dict[str, Any]:
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage import FileAccessMode, StorageFile

        engine = OcrEngine.try_create_from_language(Language("en-US"))
        if engine is None:
            engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            return {"ok": False, "error": "no OCR language pack installed", "text": "", "lines": []}

        file = await StorageFile.get_file_from_path_async(str(image_path))
        stream = await file.open_async(FileAccessMode.READ)
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        result = await engine.recognize_async(bitmap)

        lines = []
        for line in result.lines:
            words = list(line.words)
            box = None
            if words:
                rects = [w.bounding_rect for w in words]
                left = min(r.x for r in rects)
                top = min(r.y for r in rects)
                right = max(r.x + r.width for r in rects)
                bottom = max(r.y + r.height for r in rects)
                box = [int(left), int(top), int(right - left), int(bottom - top)]
            lines.append({"text": line.text, "box": box})
        return {"ok": True, "text": result.text or "", "lines": lines}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.debug("Windows OCR failed: %s", exc)
        return {"ok": False, "error": str(exc), "text": "", "lines": []}


# --------------------------------------------------------------------------- snapshot
def snapshot(
    max_elements: int = MAX_ELEMENTS,
    with_ocr: bool = True,
    with_image: bool = False,
    handle: Optional[int] = None,
) -> Dict[str, Any]:
    """Everything known about the screen right now, locally and quickly."""
    started = time.time()
    window: Dict[str, Any] = {}
    elements: List[Dict[str, Any]] = []
    errors: List[str] = []
    shot: Dict[str, Any] = {}

    try:
        from jarvis import desktop_input

        window = desktop_input.active_window()
        if not handle:
            handle = int(window.get("hwnd") or 0) or None
    except Exception as exc:
        errors.append("windows: %s" % exc)

    if _uia_ready():
        try:
            elements = _collect_elements(handle=handle, max_elements=max_elements)
        except Exception as exc:
            errors.append("uia: %s" % exc)
    else:
        errors.append("uia: pywinauto is not installed")

    ocr: Dict[str, Any] = {"ok": False, "text": "", "lines": [], "error": "skipped"}
    if with_ocr:
        try:
            shot = screenshot(window_only=True)
            ocr = _ocr(shot["path"])
        except Exception as exc:
            errors.append("ocr: %s" % exc)
    elif with_image:
        try:
            shot = screenshot(window_only=True)
        except Exception as exc:
            errors.append("screenshot: %s" % exc)

    data = {
        "ok": True,
        "window": window,
        "elements": elements,
        "element_count": len(elements),
        "text": ocr.get("text", ""),
        "lines": ocr.get("lines", []),
        "ocr": {"ok": bool(ocr.get("ok")), "error": ocr.get("error", "")},
        "image": shot.get("path", ""),
        "bbox": shot.get("bbox"),
        "errors": errors,
        "elapsed_ms": int((time.time() - started) * 1000),
        "at": time.time(),
    }
    _last_snapshot["at"] = data["at"]
    _last_snapshot["data"] = data
    return data


def cached(max_age: float = 3.0) -> Optional[Dict[str, Any]]:
    """The last snapshot when it is still fresh enough to act on."""
    data = _last_snapshot.get("data")
    if data and (time.time() - float(_last_snapshot.get("at") or 0)) <= max_age:
        return data
    return None


# --------------------------------------------------------------------------- finding + clicking
def _score(name: str, needle: str) -> int:
    a, b = name.lower().strip(), needle.lower().strip()
    if not a or not b:
        return 0
    if a == b:
        return 100
    if a.startswith(b):
        return 80
    if b in a:
        return 60
    if a in b:
        return 40
    # word overlap, e.g. "Save changes" for "save"
    overlap = set(a.replace("-", " ").split()) & set(b.replace("-", " ").split())
    return 20 + len(overlap) * 5 if overlap else 0


def find(name: str, data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Best matching on-screen element for a spoken label."""
    data = data or cached(3.0) or snapshot()
    best: Optional[Dict[str, Any]] = None
    best_score = 0
    for el in data.get("elements") or []:
        score = _score(el.get("name", ""), name)
        if score > best_score:
            best, best_score = el, score
    if best and best_score >= 40:
        best = dict(best)
        best["score"] = best_score
        return best
    # Fall back to OCR text. OCR boxes are relative to the captured window, so
    # shift them back into screen coordinates before clicking.
    bbox = data.get("bbox")
    off_x = int(bbox[0]) if bbox else 0
    off_y = int(bbox[1]) if bbox else 0
    for line in data.get("lines") or []:
        score = _score(line.get("text", ""), name)
        if score >= 40 and line.get("box"):
            x, y, w, h = line["box"]
            x, y = x + off_x, y + off_y
            return {"name": line.get("text", ""), "type": "Text",
                    "center": [x + w // 2, y + h // 2],
                    "x": x, "y": y, "width": w, "height": h,
                    "enabled": True, "score": score, "source": "ocr"}
    return None


def click_element(name: str, double: bool = False) -> Dict[str, Any]:
    """Click a named control: UIA Invoke first, real mouse click as fallback."""
    from jarvis import desktop_input

    data = snapshot(max_elements=MAX_ELEMENTS, with_ocr=True)
    target = find(name, data)
    if not target:
        return {"ok": False, "error": "I cannot see anything called %r on screen" % name,
                "window": data.get("window", {}).get("title")}

    # Prefer the accessibility action: it works even when the window is covered.
    handle = data.get("window", {}).get("hwnd")
    if handle:
        try:
            from pywinauto import Desktop

            wrapper = Desktop(backend="uia").window(handle=handle)
            for el in wrapper.descendants():
                try:
                    if (el.element_info.name or "").strip().lower() == target["name"].strip().lower():
                        el.invoke()
                        return {"ok": True, "via": "uia-invoke", "name": target["name"], "type": target.get("type")}
                except Exception:
                    break
        except Exception:
            pass

    x, y = target["center"]
    desktop_input.click(x, y, double=double)
    return {"ok": True, "via": "mouse", "name": target["name"], "at": [x, y], "type": target.get("type")}


def describe(data: Optional[Dict[str, Any]] = None, limit: int = 12) -> str:
    """A short spoken summary of the screen."""
    data = data or cached(3.0) or snapshot()
    window = (data.get("window") or {}).get("title") or "the desktop"
    parts = []
    clickable = [e for e in data.get("elements") or [] if e.get("type") in (
        "Button", "MenuItem", "Hyperlink", "TabItem", "ListItem", "CheckBox", "RadioButton")]
    names: List[str] = []
    for el in clickable:
        label = el.get("name", "").strip()
        if label and label not in names:
            names.append(label)
    if names:
        parts.append("I can see %d controls: %s" % (len(names), ", ".join(names[:limit])))
    snippet = " ".join((data.get("text") or "").split())[:220]
    if snippet:
        parts.append("On screen it reads: %s" % snippet)
    if not parts:
        parts.append("I can see %s, but no labelled controls." % window)
    return "You are in %s. %s" % (window, " ".join(parts))


def describe_with_vision(prompt: Optional[str] = None) -> Dict[str, Any]:
    """Explicit vision fallback: one screenshot, one model call, on request only."""
    try:
        from jarvis import vision

        image = screenshot_bytes()
        result = vision.describe_image(
            image,
            prompt or "Describe what is on this Windows screen and what the user is doing. Two sentences.",
        )
        result["image_bytes"] = len(image)
        return result
    except Exception as exc:
        return {"ok": False, "description": "", "error": str(exc)}
