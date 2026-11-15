"""WhatsApp driver - real calls and messages from the WhatsApp app on this PC.

This machine has the WhatsApp desktop app installed and signed in, so the
assistant drives that app instead of a website:

* ``whatsapp://send?phone=<number>`` opens the chat for that number.
* The app exposes a full UI Automation tree (a WinUI shell around a WebView2
  document), so the driver can find the message composer, paste the text, press
  **Send**, and press the **Voice call** button in the chat header.

Safety: only the numbers on the owner's allowlist may be contacted
(``whatsapp_allowed_numbers``). Everything else is refused, so a misheard digit
can never reach a stranger.

Every result says exactly what happened - "sent", "typed but not sent", "opened
the chat", or "refused" - because a call that never rang must never be
reported as a call that did.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.wa")

CONTACTS_PATH = Path.home() / ".jarvis" / "contacts.json"
DEFAULT_COUNTRY = "+91"
WA_WINDOW_TITLE = "WhatsApp"
WA_WINDOW_CLASS = "WinUIDesktopWin32WindowClass"

OPEN_TIMEOUT = 15.0
COMPOSER_PREFIX = "Type a message"


# --------------------------------------------------------------------- helpers
def _setting(name: str, default: Any = None) -> Any:
    try:
        from jarvis import settings

        return settings.get(name, default)
    except Exception:
        return default


def normalize_number(raw: str, default_country: str = DEFAULT_COUNTRY) -> str:
    """Turn '98765 43210', '+91 98765-43210' into '+919876543210'."""
    text = str(raw or "").strip()
    if not text:
        return ""
    plus = text.startswith("+")
    digits = re.sub(r"\D", "", text)
    if not digits:
        return ""
    if plus:
        return "+" + digits
    # Strip a domestic trunk prefix (082, 044, ...) before the country code.
    if digits.startswith("0"):
        rest = digits[1:]
        if len(rest) == 10:
            return default_country + rest
        if len(rest) == 12 and rest.startswith("91"):
            return "+" + rest
        if len(rest) > 10:
            # STD code + mobile number: the mobile is the last ten digits.
            return default_country + rest[-10:]
    if len(digits) == 10:
        return default_country + digits
    if len(digits) == 12 and digits.startswith("91"):
        return "+" + digits
    if len(digits) == 13 and digits.startswith("091"):
        return default_country + digits[3:]
    return "+" + digits


def looks_like_number(text: str) -> bool:
    return bool(re.fullmatch(r"[+\d][\d\s\-().]{4,}", str(text or "").strip()))


# ------------------------------------------------------------------- allowlist
def allowed_numbers() -> List[str]:
    """Numbers the assistant is allowed to message or call."""
    raw = _setting("whatsapp_allowed_numbers", [])
    if isinstance(raw, str):
        raw = [part for part in re.split(r"[,;\s]+", raw) if part]
    if not isinstance(raw, (list, tuple)):
        raw = []
    out: List[str] = []
    for item in raw:
        number = normalize_number(str(item))
        if number and number not in out:
            out.append(number)
    return out


def is_allowed(number: str) -> bool:
    target = normalize_number(number)
    if not target:
        return False
    return target in allowed_numbers()


def allow_number(number: str) -> List[str]:
    """Add a number to the allowlist (owner action only)."""
    target = normalize_number(number)
    if not target:
        return allowed_numbers()
    current = allowed_numbers()
    if target not in current:
        current.append(target)
    try:
        from jarvis import settings

        settings.set("whatsapp_allowed_numbers", current)
    except Exception:
        pass
    return current


def allow_check(number: str) -> Dict[str, Any]:
    """Guard used before every message and call."""
    if not is_allowed(number):
        allowed = allowed_numbers()
        return {
            "ok": False,
            "allowed": False,
            "number": normalize_number(number),
            "error": "{0} is not on your allowed list. Allowed: {1}. Say 'allow {0}' to add it.".format(
                normalize_number(number) or number, ", ".join(allowed) if allowed else "none"
            ),
            "message": "{0} is not on your allowed list, sir. I will not contact it.".format(
                normalize_number(number) or number
            ),
        }
    return {"ok": True, "allowed": True, "number": normalize_number(number)}


# -------------------------------------------------------------------- contacts
def load_contacts() -> Dict[str, str]:
    try:
        if CONTACTS_PATH.exists():
            data = json.loads(CONTACTS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def save_contact(name: str, number: str) -> Dict[str, str]:
    data = load_contacts()
    data[str(name).strip()] = normalize_number(number)
    CONTACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTACTS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def _match_contact(query: str) -> Optional[str]:
    query = str(query or "").strip().lower()
    if not query:
        return None
    contacts = load_contacts()
    for name, number in contacts.items():
        if name.lower() == query:
            return number
    for name, number in contacts.items():
        if query in name.lower() or name.lower() in query:
            return number
    return None


# --------------------------------------------------------------- app plumbing
def _desktop():
    try:
        from pywinauto import Desktop

        return Desktop(backend="uia")
    except Exception as exc:
        logger.debug("pywinauto unavailable: %s", exc)
        return None


def app_running() -> bool:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq WhatsApp.Root.exe"],
            capture_output=True, text=True, timeout=15,
        )
        return "WhatsApp.Root.exe" in (out.stdout or "")
    except Exception:
        return False


def protocol_available() -> bool:
    """True when Windows knows the whatsapp:// handler."""
    if os.name != "nt":
        return False
    try:
        import winreg
    except Exception:
        return False
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, r"Software\Classes\whatsapp\shell\open\command") as key:
                value, _ = winreg.QueryValueEx(key, "")
                if value:
                    return True
        except OSError:
            pass
        try:
            with winreg.OpenKey(hive, r"Software\Classes\whatsapp") as key:
                value, _ = winreg.QueryValueEx(key, "URL Protocol")
                if value is not None:
                    return True
        except OSError:
            pass
    return False


def _launch_uri(uri: str) -> bool:
    """Open a whatsapp:// URI through the shell (never via cmd: an unescaped '&'
    would be read as a command separator)."""
    try:
        os.startfile(uri)
        return True
    except Exception:
        pass
    try:
        subprocess.Popen(["explorer.exe", uri], shell=False)
        return True
    except Exception as exc:
        logger.warning("could not open %s: %s", uri, exc)
        return False


def find_window(auto_open: bool = True):
    """Return the WhatsApp window (restoring it if it was minimised)."""
    desktop = _desktop()
    if desktop is None:
        return None
    try:
        windows = desktop.windows()
    except Exception:
        return None
    fallback = None
    for win in windows:
        try:
            title = win.window_text() or ""
            cls = win.class_name() or ""
            if title == WA_WINDOW_TITLE and cls == WA_WINDOW_CLASS:
                return win
            if title == WA_WINDOW_TITLE and fallback is None:
                fallback = win
        except Exception:
            continue
    if fallback is None and auto_open:
        _launch_uri("whatsapp:")
        time.sleep(2.0)
        return find_window(auto_open=False)
    return fallback


def _focus(win) -> bool:
    if win is None:
        return False
    try:
        win.set_focus()
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetForegroundWindow(win.handle)
        except Exception:
            return False
    try:
        rect = win.rectangle()
        if rect.left < -1000:  # minimised
            import ctypes

            ctypes.windll.user32.ShowWindow(win.handle, 9)  # SW_RESTORE
    except Exception:
        pass
    return True


def _send_keys(keys: str) -> bool:
    try:
        from pywinauto.keyboard import send_keys

        send_keys(keys)
        return True
    except Exception as exc:
        logger.debug("send_keys failed: %s", exc)
        return False


def _clipboard_set(text: str) -> bool:
    try:
        import win32clipboard

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(str(text))
        win32clipboard.CloseClipboard()
        return True
    except Exception as exc:
        logger.debug("clipboard failed: %s", exc)
        return False


# ------------------------------------------------------------- element access
def _pick(items, predicate):
    """First element whose accessible name satisfies the predicate."""
    for item in items:
        try:
            name = item.element_info.name or ""
        except Exception:
            continue
        if predicate(name):
            return item, name
    return None, ""


def _buttons(win) -> List[Any]:
    try:
        return win.descendants(control_type="Button")
    except Exception as exc:
        logger.debug("button scan failed: %s", exc)
        return []


def _edits(win) -> List[Any]:
    try:
        return win.descendants(control_type="Edit")
    except Exception:
        return []


def _composer(win) -> Tuple[Any, str]:
    edit, name = _pick(_edits(win), lambda n: n.startswith(COMPOSER_PREFIX))
    return edit, name


def _composer_text(edit) -> str:
    try:
        return edit.get_value() or ""
    except Exception:
        try:
            texts = edit.texts()
            return texts[0] if texts else ""
        except Exception:
            return ""


def _chat_contact_name(win) -> str:
    """The contact name shown in the chat header (e.g. 'AVINASH')."""
    btn, name = _pick(_buttons(win), lambda n: n.startswith("Contact info"))
    if name:
        return name.replace("Contact info", "").strip()
    return ""


def _not_on_whatsapp(win) -> bool:
    try:
        texts = win.descendants(control_type="Text")
    except Exception:
        return False
    _, name = _pick(texts, lambda n: "isn't on whatsapp" in n.lower() or "is not on whatsapp" in n.lower())
    return bool(name)


def _chat_rows(win) -> List[str]:
    """The visible rows of the chat list (name + last message)."""
    try:
        items = win.descendants(control_type="DataItem")
    except Exception:
        return []
    rows = []
    seen = set()
    for item in items:
        try:
            name = (item.element_info.name or "").strip()
        except Exception:
            continue
        if not name or name in seen:
            continue
        seen.add(name)
        rows.append(name)
    return rows


def _number_from_chat_list(query: str) -> Optional[str]:
    """Find a chat whose row shows a number that matches the query."""
    query = str(query or "").strip().lower()
    if not query:
        return None
    win = find_window()
    if win is None:
        return None
    for row in _chat_rows(win):
        low = row.lower()
        if query not in low:
            continue
        m = re.search(r"(\+?\d[\d ]{7,}\d)", row)
        if m:
            number = normalize_number(m.group(1))
            if number:
                return number
    return None


def get_chat_list() -> List[Dict[str, Any]]:
    """Parse all visible chats from WhatsApp with sender, unread_count, preview, time."""
    win = find_window()
    if not win:
        return []
    rows = _chat_rows(win)
    raw_rows = [re.sub(r"\s+", " ", r).strip() for r in rows if r.strip()]

    chats = []
    i = 0
    while i < len(raw_rows):
        curr = raw_rows[i]
        if i + 1 < len(raw_rows):
            nxt = raw_rows[i + 1]
            if nxt in curr and len(curr) > len(nxt):
                header = nxt
                msg = curr[len(nxt):].strip()
                chats.append({"header": header, "preview": msg, "full": curr})
                i += 2
                continue
            elif curr in nxt and len(nxt) > len(curr):
                header = curr
                msg = nxt[len(curr):].strip()
                chats.append({"header": header, "preview": msg, "full": nxt})
                i += 2
                continue
        chats.append({"header": curr, "preview": "", "full": curr})
        i += 1

    results = []
    for c in chats:
        hdr = c["header"]
        full = c["full"]
        preview = c["preview"]

        unread_match = re.search(r"(\d+)\s+unread\s+messages?", full, re.IGNORECASE)
        unread_count = int(unread_match.group(1)) if unread_match else 0

        cleaned_hdr = re.sub(r"^\d+\s+unread\s+messages?\s*", "", hdr, flags=re.IGNORECASE)
        time_match = re.search(
            r"\b(Today|Yesterday|Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|\d{1,2}:\d{2}\s*(?:am|pm)?|\d{1,2}/\d{1,2}/\d{2,4})\b",
            cleaned_hdr,
            re.IGNORECASE,
        )
        time_str = time_match.group(1) if time_match else ""
        if time_match:
            sender = cleaned_hdr[: time_match.start()].strip()
        else:
            sender = cleaned_hdr.strip()
        if not sender:
            sender = cleaned_hdr

        results.append({
            "sender": sender,
            "unread_count": unread_count,
            "preview": preview,
            "time": time_str,
            "raw": full,
        })
    return results


def _clean_for_speech(text: str) -> str:
    """Normalize symbols so TTS (edge-tts) can pronounce them cleanly."""
    if not text:
        return ""
    t = str(text)
    t = t.replace("₹", " rupees ").replace("$", " dollars ").replace("€", " euros ")
    t = t.replace("\xa0", " ").replace("~", "").replace("⚠️", "Warning: ")
    # Collapse spaces
    t = re.sub(r"\s+", " ", t).strip()
    return t


def get_unread_messages() -> Dict[str, Any]:
    """Retrieve and summarize unread WhatsApp messages."""
    chats = get_chat_list()
    unreads = [c for c in chats if c.get("unread_count", 0) > 0]
    total_unreads = sum(c.get("unread_count", 0) for c in unreads)

    if not unreads:
        return {
            "ok": True,
            "count": 0,
            "chats": [],
            "message": "You have no unread messages on WhatsApp, sir.",
        }

    parts = []
    for u in unreads[:5]:
        sender = u["sender"]
        cnt = u["unread_count"]
        cnt_str = f"{cnt} messages" if cnt > 1 else "1 message"
        prev = _clean_for_speech(u["preview"])
        if prev:
            prev_snippet = prev[:60] + ("..." if len(prev) > 60 else "")
            parts.append(f"{cnt_str} from {sender}: '{prev_snippet}'")
        else:
            parts.append(f"{cnt_str} from {sender}")

    summary = (
        f"You have {total_unreads} unread messages across {len(unreads)} chats, sir. "
        + "; ".join(parts)
        + "."
    )
    return {
        "ok": True,
        "count": total_unreads,
        "chats_count": len(unreads),
        "unreads": unreads,
        "message": summary,
    }


def get_recent_messages(limit: int = 5) -> Dict[str, Any]:
    """Retrieve and summarize recent WhatsApp messages."""
    chats = get_chat_list()
    if not chats:
        return {
            "ok": False,
            "error": "Could not access WhatsApp chats.",
            "message": "I could not retrieve recent messages from WhatsApp, sir.",
        }

    recent = chats[:limit]
    parts = []
    for r in recent:
        sender = r["sender"]
        prev = _clean_for_speech(r["preview"]) or "recent activity"
        prev_snippet = prev[:50] + ("..." if len(prev) > 50 else "")
        t_str = f" ({r['time']})" if r.get("time") else ""
        parts.append(f"from {sender}{t_str}: '{prev_snippet}'")

    summary = "Your recent WhatsApp messages, sir: " + "; ".join(parts) + "."
    return {
        "ok": True,
        "count": len(recent),
        "messages": recent,
        "message": summary,
    }


def read_contact_message(contact: str) -> Dict[str, Any]:
    """Find and read latest message from a specific contact."""
    target_clean = contact.lower().strip()
    chats = get_chat_list()
    found = None
    for c in chats:
        if target_clean in c["sender"].lower() or c["sender"].lower() in target_clean:
            found = c
            break

    if not found:
        return {
            "ok": False,
            "error": f"No recent chat found for '{contact}'.",
            "message": f"I could not find any recent messages from {contact} on WhatsApp, sir.",
        }

    prev = _clean_for_speech(found["preview"])
    t_str = f" from {found['time']}" if found.get("time") else ""
    if prev:
        msg = f"The latest message from {found['sender']}{t_str} says: '{prev}', sir."
    else:
        msg = f"Found chat with {found['sender']}{t_str}, but no message text was visible, sir."

    return {
        "ok": True,
        "sender": found["sender"],
        "time": found["time"],
        "preview": prev,
        "unread_count": found["unread_count"],
        "message": msg,
    }


def resolve_target(target: str) -> Dict[str, Any]:
    """Resolve a spoken target ('avinash', '+91 98765 43210') to a number."""
    raw = str(target or "").strip()
    if not raw:
        return {"ok": False, "error": "no contact or number given"}

    if looks_like_number(raw):
        number = normalize_number(raw)
        if number:
            return {"ok": True, "number": number, "source": "number"}

    stored = _match_contact(raw)
    if stored:
        return {"ok": True, "number": stored, "source": "contacts"}

    found = _number_from_chat_list(raw)
    if found:
        try:
            save_contact(raw, found)
        except Exception:
            pass
        return {"ok": True, "number": found, "source": "whatsapp-chatlist"}

    return {
        "ok": False,
        "error": (
            "I do not have a number for '{0}'. Say 'remember {0} as <number>' once "
            "and I will know it from now on.".format(raw)
        ),
    }


# ------------------------------------------------------------------- messaging
def send_message(target: str, text: str, auto_send: bool = True) -> Dict[str, Any]:
    """Send a WhatsApp message. Returns an honest report."""
    message_text = str(text or "").strip()
    if not message_text:
        return {"ok": False, "error": "no message text given"}

    resolved = resolve_target(target)
    if not resolved.get("ok"):
        return {"ok": False, "error": resolved.get("error")}
    number = resolved["number"]

    guard = allow_check(number)
    if not guard.get("ok"):
        return {"ok": False, "sent": False, "channel": "whatsapp-desktop", **guard}

    uri = "whatsapp://send?phone={0}".format(urllib.parse.quote(number, safe="+"))
    if not _launch_uri(uri):
        return {"ok": False, "error": "WhatsApp could not be opened"}

    win = find_window()
    if win is not None:
        _focus(win)
    time.sleep(1.5)
    win = find_window() or win
    if win is None:
        return {"ok": False, "sent": False, "channel": "whatsapp-desktop",
                "error": "the WhatsApp window could not be found"}

    _focus(win)
    if _not_on_whatsapp(win):
        return {
            "ok": False, "number": number, "text": message_text, "sent": False,
            "channel": "whatsapp-desktop",
            "error": "{0} is not on WhatsApp.".format(number),
            "message": "{0} is not on WhatsApp, sir.".format(number),
        }

    edit, composer_name = _composer(win)
    if edit is None:
        return {
            "ok": False, "number": number, "text": message_text, "sent": False,
            "channel": "whatsapp-desktop",
            "error": "WhatsApp opened, but the message box was not ready.",
            "message": "WhatsApp opened {0}, sir, but I could not reach the message box.".format(number),
        }

    contact = composer_name.replace(COMPOSER_PREFIX, "").replace("to", "").strip()
    if contact:
        contact = contact[0] if len(contact) <= 2 else contact

    try:
        edit.click_input()
    except Exception:
        pass
    time.sleep(0.3)
    current = _composer_text(edit)
    if message_text[:20] not in current:
        if _clipboard_set(message_text):
            _send_keys("^v")
            time.sleep(0.6)

    sent = False
    if auto_send:
        btn, _ = _pick(_buttons(win), lambda n: n.strip() == "Send")
        if btn is not None:
            try:
                btn.click_input()
                sent = True
            except Exception as exc:
                logger.debug("send click failed: %s", exc)
        if not sent:
            sent = _send_keys("{ENTER}")
        time.sleep(1.0)
        after = _composer_text(edit)
        if after and message_text[:20] in after:
            sent = False

    detail = "sent" if sent else "typed in WhatsApp - press Enter to send"
    return {
        "ok": True,
        "number": number,
        "contact": contact,
        "text": message_text,
        "sent": sent,
        "channel": "whatsapp-desktop",
        "message": "WhatsApp message to {0} {1}.".format(contact or number, detail),
    }


def start_call(target: str, wait: float = 2.0, video: bool = False) -> Dict[str, Any]:
    """Start a WhatsApp voice (or video) call through the app."""
    resolved = resolve_target(target)
    if not resolved.get("ok"):
        return {"ok": False, "error": resolved.get("error")}
    number = resolved["number"]

    guard = allow_check(number)
    if not guard.get("ok"):
        return {"ok": False, "placed": False, "channel": "whatsapp-desktop", **guard}

    uri = "whatsapp://send?phone={0}".format(urllib.parse.quote(number, safe="+"))
    if not _launch_uri(uri):
        return {"ok": False, "error": "WhatsApp could not be opened"}

    win = find_window()
    if win is not None:
        _focus(win)
    time.sleep(1.5)
    win = find_window() or win
    if win is None:
        return {"ok": False, "number": number, "placed": False, "channel": "whatsapp-desktop",
                "error": "the WhatsApp window could not be found",
                "message": "I could not open WhatsApp, sir."}

    _focus(win)
    if _not_on_whatsapp(win):
        return {
            "ok": False, "number": number, "placed": False, "channel": "whatsapp-desktop",
            "error": "{0} is not on WhatsApp.".format(number),
            "message": "{0} is not on WhatsApp, sir.".format(number),
        }

    contact = _chat_contact_name(win)
    wanted = "Video call" if video else "Voice call"
    btn, _ = _pick(_buttons(win), lambda n: n.strip() == wanted)
    if btn is None:
        return {
            "ok": False, "number": number, "contact": contact, "placed": False,
            "channel": "whatsapp-desktop",
            "error": "WhatsApp opened {0} but it offers no {1} button.".format(contact or number, wanted),
            "message": "I opened {0} in WhatsApp, sir, but there is no call button to press.".format(
                contact or number
            ),
        }
    try:
        btn.click_input()
    except Exception as exc:
        logger.debug("call click failed: %s", exc)
        return {
            "ok": False, "number": number, "contact": contact, "placed": False,
            "channel": "whatsapp-desktop",
            "error": "the call button could not be pressed: {0}".format(exc),
            "message": "I could not press the call button, sir.",
        }

    time.sleep(wait)
    return {
        "ok": True,
        "number": number,
        "contact": contact,
        "placed": True,
        "video": video,
        "channel": "whatsapp-desktop",
        "message": "Calling {0} on WhatsApp.".format(contact or number),
    }


def status() -> Dict[str, Any]:
    running = app_running()
    win = find_window()
    contacts = load_contacts()
    return {
        "app_running": running,
        "window": bool(win),
        "protocol": protocol_available(),
        "saved_contacts": len(contacts),
        "allowed_numbers": allowed_numbers(),
        "contacts": contacts,
        "ready": running or protocol_available(),
    }


__all__ = [
    "send_message",
    "start_call",
    "resolve_target",
    "normalize_number",
    "looks_like_number",
    "save_contact",
    "load_contacts",
    "status",
    "app_running",
    "protocol_available",
    "allowed_numbers",
    "is_allowed",
    "allow_number",
    "allow_check",
    "get_chat_list",
    "get_unread_messages",
    "get_recent_messages",
    "read_contact_message",
]
