"""Natural-language PC intent parsing.

Turns a spoken or typed instruction into concrete ``pc_control`` tool calls.
This runs before any AI model, so the assistant can act on the PC instantly and
for free - no quota, no round trip, and it still works while the brain is off.

Every parser returns tool actions in the same shape the daemon already
executes::

    {"tool": "pc_control", "args": {"action": "open_app", "target": "chrome"}}

Matching runs against the *original* text with ``re.IGNORECASE`` so Windows
paths keep their capitalisation.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

TOOL = "pc_control"

_TRAILING = " \t\n\r.,;:!?\"'"
_I = re.IGNORECASE

_URL_RE = re.compile(r"^(?:https?://)?(?:www\.)?[\w-]+(?:\.[\w-]+)+(?:/[^\s]*)?$")

# Words that name something in the HUD, not an application on the PC.
# "close help" and "exit vr" are UI commands, not "close an app called help".
_UI_TARGETS = {
    "help", "settings", "voice test", "pc control", "pc control panel",
    "panel", "hud", "ar", "vr", "xr", "immersive", "immersive mode",
    "hologram", "agents", "agent hub", "phone", "call", "core", "bike",
    "car", "everything", "all", "the browser", "log", "command log",
    # HUD agents live in the interface, not in a desktop window.
    "jarvis", "friday", "edith", "codex", "ollama", "local mode", "cloud mode",
    "local", "cloud", "the ai", "ai mode",
}


def _clean_path(text: str) -> str:
    value = (text or "").strip().strip("\"'").strip(_TRAILING)
    for _ in range(3):
        new = re.sub(
            r"^(?:the\s+)?(?:file|folder|directory|document)\s+(?:called|named)\s+",
            "", value, flags=_I,
        )
        new = re.sub(r"^(?:the\s+)?(?:file|folder|directory|document)\s+", "", new, flags=_I)
        new = re.sub(r"^(?:called|named)\s+", "", new, flags=_I)
        if new == value:
            break
        value = new
    return value.strip().strip(_TRAILING)


def _clean_target(text: str) -> str:
    value = (text or "").strip().strip("\"'").strip(_TRAILING)
    value = re.sub(r"^(?:the\s+|my\s+|a\s+|an\s+)", "", value, flags=_I)
    return value.strip().strip(_TRAILING)


_KEY_ALIASES = {
    "control": "ctrl", "ctl": "ctrl", "windows": "win", "escape": "esc",
    "return": "enter", "del": "delete", "arrow up": "up", "arrow down": "down",
    "arrow left": "left", "arrow right": "right", "spacebar": "space",
    "dot": "period", "full stop": "period",
}


def _clean_keys(text: str) -> str:
    """Turn spoken key names into a combo the input layer understands."""
    raw = str(text or "").strip().strip(_TRAILING).lower()
    if not raw:
        return ""
    raw = re.sub(r"\s+(?:key|button|keys)$", "", raw).strip()
    raw = raw.replace(" + ", "+").replace(" plus ", "+").replace(" and ", "+")
    for word, key in _KEY_ALIASES.items():
        raw = re.sub(r"\b%s\b" % re.escape(word), key, raw)
    parts = [p.strip() for p in raw.split("+") if p.strip()]
    if len(parts) > 1:
        return "+".join(parts)
    # "control s", "shift tab" - modifier followed by its key.
    tokens = raw.split()
    if len(tokens) == 2 and tokens[0] in ("ctrl", "shift", "alt", "win"):
        return tokens[0] + "+" + tokens[1]
    return raw.replace(" ", "")


def _action(name: str, **args: Any) -> Dict[str, Any]:
    return {"tool": TOOL, "args": dict(action=name, **args)}


def _action_whatsapp(action: str, **args: Any) -> Dict[str, Any]:
    return {"tool": "whatsapp", "args": dict(action=action, **args)}


def _looks_like_url(text: str) -> bool:
    value = (text or "").strip()
    if not value or " " in value:
        return False
    if value.lower().startswith(("http://", "https://")):
        return True
    return bool(_URL_RE.match(value))


def detect(text: str) -> List[Dict[str, Any]]:
    """Parse an instruction into PC control actions (may be empty)."""
    raw = (text or "").strip()
    if not raw:
        return []
    t = re.sub(r"\s+", " ", raw.lower())

    # ---- email & calendar (only where credentials are configured) --------
    if re.search(r"\b(?:what(?:'s| is) on (?:my|the) calendar|my (?:schedule|calendar)(?: for today)?|today'?s (?:schedule|calendar|meetings)|any (?:meetings|events) today)\b", t):
        return [_action("calendar")]
    if re.search(r"\b(?:check|read|show|any|get)\b[^.]{0,14}\b(?:unread\s+)?(?:e-?mails?|inbox)\b", t) or \
       re.search(r"\bunread e-?mails?\b", t):
        return [_action("read_email")]
    m = re.search(
        r"\b(?:send|write|draft)\s+(?:an?\s+)?e-?mail\b\s*(?:to\s+)?(?P<to>[^\s,]{3,90})"
        r"(?:[,. ]+\s*(?:about|saying|with|subject)\s+(?P<b>.*))?$",
        raw, _I,
    )
    if m:
        to = _clean_target(m.group("to"))
        body = (m.group("b") or "").strip().strip(_TRAILING)
        if to:
            return [_action("send_email", to=to, subject=(body[:60] or "Message from JARVIS"), body=body)]

    # ---- WhatsApp: reading messages --------------------------------------
    if re.search(r"\b(?:unread\s+(?:whatsapp\s+)?messages?|what\s+are\s+my\s+unread|check\s+(?:my\s+)?unread|read\s+(?:my\s+)?unread|any\s+unread\s+messages?|tell\s+me\s+my\s+unread)\b", t):
        return [_action_whatsapp("unread_messages")]

    if re.search(r"\b(?:recent\s+(?:whatsapp\s+)?messages?|what\s+are\s+my\s+recent|check\s+(?:my\s+)?recent|read\s+(?:my\s+)?recent|latest\s+(?:whatsapp\s+)?messages?|tell\s+me\s+recent\s+messages?)\b", t):
        return [_action_whatsapp("recent_messages")]

    m = re.search(r"\b(?:read|check|show|tell\s+me)\s+(?:whatsapp\s+)?messages?\s+from\s+(?P<c>.+)$", raw, _I)
    if not m:
        m = re.search(r"\bwhat\s+did\s+(?P<c>.+?)\s+(?:say|send|message|text)(?:\s+(?:on|via)\s+whatsapp)?\b", raw, _I)
    if m:
        contact = _clean_target(m.group("c"))
        contact = re.sub(r"^(?:on|via|over)\s+whatsapp\s+", "", contact, flags=_I).strip()
        contact = re.sub(r"\s+(?:on|via|over|using)\s+whatsapp$", "", contact, flags=_I).strip()
        if contact and contact.lower() not in _UI_TARGETS:
            return [_action_whatsapp("read_contact", target=contact)]

    if re.search(r"\b(?:read|check)\s+(?:my\s+)?(?:whatsapp\s+)?messages?\b", t) or \
       re.search(r"\b(?:check|read)\s+(?:my\s+)?whatsapp\b", t):
        return [_action_whatsapp("unread_messages")]

    # ---- WhatsApp: calls and messages ------------------------------------
    m = re.search(
        r"\b(?:send\s+(?:a\s+)?(?:whatsapp\s+)?message\s+to|message|whatsapp|text|reply)\s+"
        r"(?P<t>[^,]{1,60}?)\s+(?:saying|that says|with|and say|and write|message)\s+(?P<m>.+)$",
        raw, _I,
    )
    if not m:
        m = re.search(
            r"\bsend\s+(?:a\s+)?(?:whatsapp\s+)?message\s+(?:to\s+)?(?P<t>[^,]{1,60}?)\s*[:\-]\s*(?P<m>.+)$",
            raw, _I,
    )
    if m:
        who = _clean_target(m.group("t"))
        body = m.group("m").strip().strip(_TRAILING)
        if who and body:
            return [_action_whatsapp("send_message", target=who, text=body)]

    # "message mom i am on my way" / "text ravi meeting at 5"
    m = re.search(
        r"^\s*(?:send\s+(?:a\s+)?)?(?:whatsapp\s+)?(?:message|text|msg)\s+"
        r"(?P<t>\+?\d[\d \-]{5,}|[\w'-]+)\s+(?P<m>.+)$",
        raw, _I,
    )
    if m:
        who = _clean_target(m.group("t"))
        body = m.group("m").strip().strip(_TRAILING)
        if who and body:
            return [_action_whatsapp("send_message", target=who, text=body)]

    m = re.search(
        r"\b(?:call|phone|ring|dial)\b\s+(?:whatsapp\s+)?(?P<t>.+)$", raw, _I,
    )
    if m:
        who = _clean_target(m.group("t"))
        who = re.sub(r"^(?:on|via|over)\s+whatsapp\s+", "", who, flags=_I).strip()
        who = re.sub(r"\s+(?:on|via|over|using)\s+whatsapp$", "", who, flags=_I).strip()
        who = re.sub(r"\s+whatsapp$", "", who, flags=_I).strip()
        # "call my friend" is the demo line and "via globalfone" asks for the
        # VoIP gateway - both are handled elsewhere.
        demo = who.lower() in ("friend", "my friend", "the friend")
        voip = bool(re.search(r"\b(global\s?fone|voip|dialer)\b", t))
        if who and who.lower() not in _UI_TARGETS and not demo and not voip:
            return [_action_whatsapp("call", target=who)]

    m = re.search(
        r"\bremember\s+(?P<n>[\w .'-]{1,40}?)\s+as\s+(?P<num>\+?[\d][\d \-]{5,})$", raw, _I,
    )
    if m:
        return [_action_whatsapp("remember", name=m.group("n").strip(), number=m.group("num").strip())]

    m = re.search(
        r"\b(?:allow|add)\s+(?P<num>\+?\d[\d\-]{5,})(?:\s+(?:to|on)\s+the\s+allowed\s+list)?$",
        raw, _I,
    )
    if m:
        return [_action_whatsapp("allow", number=m.group("num").strip())]

    # ---- power -----------------------------------------------------------
    if re.search(r"\b(?:cancel|abort|stop|undo)\b[^.]{0,16}\b(?:shutdown|shut down|restart|reboot)\b", t):
        return [_action("cancel_shutdown")]
    if re.search(r"\b(?:shut\s*down|shutdown|power off)\b", t) and not re.search(r"\b(?:cancel|abort)\b", t):
        delay = 5
        m = re.search(r"\bin\s+(\d+)\s*(?:seconds?|s)\b", t)
        if m:
            delay = max(0, int(m.group(1)))
        return [_action("shutdown", delay_seconds=delay)]
    if re.search(r"\b(?:restart|reboot)\b", t):
        delay = 5
        m = re.search(r"\bin\s+(\d+)\s*(?:seconds?|s)\b", t)
        if m:
            delay = max(0, int(m.group(1)))
        return [_action("restart", delay_seconds=delay)]
    if re.search(r"\block\b[^.]{0,18}\b(?:pc|computer|screen|machine|workstation|desktop)\b", t) or \
            re.search(r"\block\s+(?:my|the)\b", t):
        return [_action("lock_screen")]
    if re.search(r"\b(?:sleep|hibernate|suspend)\b", t):
        return [_action("run_command",
                        target="rundll32.exe powrprof.dll,SetSuspendState 0,1,0")]

    # ---- screen / audio --------------------------------------------------
    if re.search(r"\b(?:screen\s?shot|capture (?:the |my )?screen|grab (?:the |my )?screen|take a picture of the screen)\b", t):
        return [_action("screenshot")]
    if re.search(r"\b(?:volume up|turn (?:the |my )?volume up|turn up (?:the |my )?volume|louder|increase (?:the )?volume|raise (?:the )?volume)\b", t):
        return [_action("volume", target="volume_up")]
    if re.search(r"\b(?:volume down|turn (?:the |my )?volume down|turn down (?:the |my )?volume|quieter|decrease (?:the )?volume|lower (?:the )?volume)\b", t):
        return [_action("volume", target="volume_down")]
    if re.search(r"\bunmute\b|\bun-?mute\b", t):
        return [_action("volume", target="unmute")]
    if re.search(r"\b(?:mute|silence)\b", t):
        return [_action("volume", target="mute")]

    # ---- processes -------------------------------------------------------
    if re.search(r"\b(?:list|show|what(?:'s| is) running)\b[^.]{0,18}\bprocess(?:es)?\b", t):
        return [_action("list_processes")]
    m = re.search(r"\b(?:kill|terminate|end)\b[^.]{0,14}\bprocess\b\s+(?P<p>.+)$", raw, _I)
    if m:
        return [_action("kill_process", target=_clean_target(m.group("p")))]

    # ---- system info -----------------------------------------------------
    if re.search(r"\b(?:system info|system status|pc stats|computer stats|sysinfo|how(?:'s| is) the (?:pc|computer) doing)\b", t):
        return [_action("system_info")]

    # ---- Dynamic island popup / bubble -----------------------------------
    if re.search(r"\b(?:open|start|show|enable|launch)\b[^.]{0,18}\b(?:bubble|popup|dynamic island|island mode|capsule)\b", t) or \
       re.search(r"\b(?:bubble|popup|dynamic island)\s+(?:mode\s+)?(?:on|start|open|show)\b", t):
        return [_action("bubble", target="open")]
    if re.search(r"\b(?:close|hide|stop|disable|quit|exit)\b[^.]{0,18}\b(?:bubble|popup|dynamic island|island mode|capsule)\b", t) or \
       re.search(r"\b(?:bubble|popup|dynamic island)\s+(?:mode\s+)?(?:off|stop|close|hide)\b", t):
        return [_action("bubble", target="close")]
    if re.search(r"\b(?:toggle|switch)\b[^.]{0,18}\b(?:bubble|popup|dynamic island|island mode|capsule)\b", t):
        return [_action("bubble", target="toggle")]

    # ---- screen awareness (local OCR + UI Automation) --------------------
    if re.search(r"\b(?:what(?:'s| is) on (?:my|the) screen|read (?:my|the) screen|describe (?:my|the) screen|screen read|what am i looking at|look at (?:my|the) screen)\b", t):
        return [_action("screen", target="describe")]
    if re.search(r"\bwhat can i click\b|\blist (?:the )?buttons\b", t):
        return [_action("screen", target="read")]

    # ---- browser automation & tabs --------------------------------------
    # Duplicate tabs cleanup
    if re.search(r"\b(?:close|remove|clean(?: up)?|shut)\b[^.]{0,18}\b(?:duplicate|repeated|extra)\s+tabs?\b", t) or \
       re.search(r"\bclose\s+(?:all\s+)?duplicate\s+tabs?\b", t):
        return [_action("browser", browser_action="close_duplicate_tabs")]

    # Open tab / new tab
    m = re.search(r"\b(?:can you\s+)?(?:please\s+)?(?:open|create|launch|start|new)\b[^.]{0,12}\b(?:new\s+)?tab\b(?:\s+(?:on|to|for|with)\s+(?P<u>\S+))?", raw, _I)
    if m:
        u = m.group("u").strip().strip(_TRAILING) if m.group("u") else ""
        return [_action("browser", browser_action="open_tab", url=u or "")]

    # Close tab
    if re.search(r"\b(?:can you\s+)?(?:please\s+)?(?:close|shut|kill|dismiss)\b[^.]{0,12}\b(?:this\s+|the\s+|current\s+)?tab\b", t):
        return [_action("browser", browser_action="close_tab")]

    # List open tabs
    if re.search(r"\b(?:list|show|what|how many)\b[^.]{0,14}\b(?:are\s+(?:my\s+)?)?tabs?\b", t):
        return [_action("browser", browser_action="list_tabs")]

    # Switch tab
    m = re.search(r"\b(?:switch|go|jump)\b[^.]{0,12}\b(?:to\s+)?(?:tab\s+(?:number\s+)?(?P<idx>\d+)|(?P<name>.+?)\s+tab)\b", raw, _I)
    if m:
        target = m.group("idx") or m.group("name")
        return [_action("browser", browser_action="switch_tab", target=target.strip())]

    # Refresh / reload
    if re.search(r"\b(?:can you\s+)?(?:please\s+)?(?:refresh|reload)\b[^.]{0,12}\b(?:the\s+)?(?:page|tab|browser|website)\b", t):
        return [_action("browser", browser_action="reload")]

    # Navigation: back / forward
    if re.search(r"\b(?:go\s+back|back\s+page|previous\s+page)\b", t):
        return [_action("browser", browser_action="back")]
    if re.search(r"\b(?:go\s+forward|forward\s+page|next\s+page)\b", t):
        return [_action("browser", browser_action="forward")]

    m = re.search(r"\b(?:browser|page|website|site)\b[^.]{0,12}\b(?:search|google|look up)\b\s+(?:for\s+)?(?P<q>.+)$", raw, _I)
    if m:
        return [_action("browser", browser_action="search", query=m.group("q").strip().strip(_TRAILING))]
    m = re.search(r"\bclick\b\s+(?:on\s+)?(?:the\s+)?(?P<n>.+?)\s+(?:on|in)\s+(?:the\s+)?(?:browser|page|website|site)\b", raw, _I)
    if m:
        return [_action("browser", browser_action="click", target=_clean_target(m.group("n")))]
    if re.search(r"\b(?:read|summar(?:ise|ize)|what(?:'s| is) on)\b[^.]{0,10}\b(?:the\s+)?(?:page|browser|website)\b", t):
        return [_action("browser", browser_action="read")]

    # ---- window management (maximize, minimize, restore, close) ----------
    m = re.search(r"\b(?:can you\s+)?(?:please\s+)?(?:maximi[sz]e)\b(?:\s+(?:the|this|my))?(?:\s+(?:window|screen|app|application))?(?:\s+(?:of\s+)?(?P<t>[^,.]+))?$", raw, _I)
    if m:
        target = _clean_target(m.group("t") or "")
        return [_action("maximize_window", target=target)]

    m = re.search(r"\b(?:can you\s+)?(?:please\s+)?(?:minimi[sz]e)\b(?:\s+(?:the|this|my))?(?:\s+(?:window|screen|app|application))?(?:\s+(?:of\s+)?(?P<t>[^,.]+))?$", raw, _I)
    if m:
        target = _clean_target(m.group("t") or "")
        return [_action("minimize_window", target=target)]

    m = re.search(r"\b(?:can you\s+)?(?:please\s+)?(?:restore)\b(?:\s+(?:the|this|my))?(?:\s+(?:window|screen|app|application))?(?:\s+(?:of\s+)?(?P<t>[^,.]+))?$", raw, _I)
    if m:
        target = _clean_target(m.group("t") or "")
        return [_action("restore_window", target=target)]

    m = re.search(r"\b(?:can you\s+)?(?:please\s+)?close\b\s+(?:the\s+|this\s+|current\s+|active\s+)?window(?:\s+(?:of\s+)?(?P<t>[^,.]+))?$", raw, _I)
    if m:
        target = _clean_target(m.group("t") or "")
        return [_action("close_window", target=target)]

    # ---- mouse, keyboard and window focus --------------------------------
    m = re.search(r"\b(?:click|tap)\b\s+(?:on\s+)?(?:the\s+)?(?P<name>.+?)(?:\s+button)?$", raw, _I)
    if m:
        name = _clean_target(m.group("name"))
        if name and name.lower() not in _UI_TARGETS:
            return [_action("screen_click", target=name)]

    m = re.search(r"\bpress\b\s+(?:the\s+)?(?P<k>[^,]{1,40})$", raw, _I)
    if m:
        raw_keys = m.group("k").strip()
        if "button" in raw_keys.lower():
            name = _clean_target(re.sub(r"\bthe\b|\bbutton\b", " ", raw_keys, flags=_I))
            if name:
                return [_action("screen_click", target=name)]
        keys = _clean_keys(raw_keys)
        if keys:
            return [_action("press_key", keys=keys)]

    m = re.search(r"\btype\b\s+(?:out\s+)?(?:the\s+text\s+|text\s+|this\s*[:\-]\s*)?(?P<x>.+)$", raw, _I)
    if not m:
        m = re.search(r"\b(?:enter|write)\s+(?:the\s+text|text)\s+(?P<x>.+)$", raw, _I)
    if m:
        text = m.group("x").strip().strip(_TRAILING)
        text = re.sub(r"\s+(?:and|then)\s+(?:press|hit)\s+(?:the\s+)?(?:key\s+)?\w+$", "", text, flags=_I)
        if text:
            out = [_action("type_text", text=text)]
            m2 = re.search(r"\b(?:and|then)\s+(?:press|hit)\s+(?:the\s+)?(?:key\s+)?(?P<k>\w+)$", raw, _I)
            if m2:
                out.append(_action("press_key", keys=_clean_keys(m2.group("k"))))
            return out

    m = re.search(r"\bscroll\s+(?P<dir>up|down|left|right)\b(?:\s+(?:by\s+)?(?P<n>\d+))?", t)
    if m:
        count = int(m.group("n") or 3)
        amount = count if m.group("dir") in ("up", "right") else -count
        return [_action("scroll", amount=amount, horizontal=m.group("dir") in ("left", "right"))]

    m = re.search(r"\b(?:switch to|focus|bring up|activate)\b\s+(?:the\s+)?(?P<w>.+?)(?:\s+window)?$", raw, _I)
    if m:
        window = _clean_target(m.group("w"))
        if window and window.lower() not in _UI_TARGETS:
            return [_action("focus_window", target=window)]
    if re.search(r"\b(?:list|show)\b[^.]{0,12}\b(?:open\s+)?windows?\b", t):
        return [_action("list_windows")]

    # ---- packages --------------------------------------------------------
    m = re.search(r"\b(?:uninstall|remove program|remove app)\b\s+(?P<p>.+)$", raw, _I)
    if m:
        package = _clean_target(m.group("p"))
        if package:
            return [_action("uninstall_app", package=package)]
    if re.search(r"\blist\b[^.]{0,14}\b(?:installed|installed apps|installed programs|applications)\b", t):
        return [_action("list_installed")]
    m = re.search(r"\b(?:install|add)\b\s+(?:the\s+)?(?:app|application|program|package)?\s*(?P<p>[^,]+)$", raw, _I)
    if m and not re.search(r"\binstall(?:ed|ing)?\b.{0,10}\bdriver\b", t):
        package = _clean_target(m.group("p"))
        if package and package.lower() not in ("app", "application", "program", "package"):
            return [_action("install_app", package=package)]
    if re.search(r"\bempty (?:the )?recycle bin\b", t):
        return [_action("empty_recycle_bin")]

    # ---- raw command -----------------------------------------------------
    m = re.search(r"\b(?:run|execute)\s+(?:the\s+)?(?:powershell|ps)\s+(?:command\s+)?(?P<c>.+)$", raw, _I)
    if m:
        return [_action("run_powershell", command=m.group("c").strip(), timeout=60)]
    m = re.search(r"\b(?:run|execute)\s+(?:the\s+)?(?:command|cmd|shell)\s+(?P<c>.+)$", raw, _I)
    if m:
        return [_action("run_command", target=m.group("c").strip(), timeout=60)]

    # ---- web -------------------------------------------------------------
    m = re.search(r"\bsearch\s+(?:the\s+)?(?:web|internet|online|google)\s+for\s+(?P<q>.+)$", raw, _I)
    if m:
        return [_action("web_search", target=m.group("q").strip())]
    m = re.search(r"\b(?:fetch|summar(?:ise|ize)|what(?:'s| is) on)\b[^.]{0,20}\b(?:web\s?page|site|page|website)\s+(?P<u>\S+)", raw, _I)
    if m:
        return [_action("web_fetch", target=m.group("u").strip())]

    # ---- files -----------------------------------------------------------
    # "write <file> with content X" / "write to <file>: X"
    m = re.search(
        r"\b(?:write|create|save|make|put)\b[^.]{0,24}\b(?:file|note|text|document)\b\s+(?P<p>.+?)"
        r"(?:\s+(?:with|containing|saying|that says|holding|saying that)\b|\s+[:\-]\s+)(?P<c>.+)$",
        raw, _I,
    )
    if m:
        path = _clean_path(m.group("p"))
        content = m.group("c").strip().strip(_TRAILING)
        # "with content hello" / "saying text hello" -> the content itself
        content = re.sub(r"^(?:content|contents|text|message|body|that says)\s+", "", content, flags=_I)
        if path and content:
            return [_action("write_file", path=path, content=content)]

    # "open the file X" opens it in its default app; "read the file X" reads it.
    m = re.search(r"\bopen\b[^.]{0,18}\b(?:the\s+)?(?:file|document)\b\s+(?P<p>.+)$", raw, _I)
    if m:
        path = _clean_path(m.group("p"))
        if path:
            return [_action("open_file", path=path)]

    m = re.search(r"\b(?:read|show me|display|print|cat)\b[^.]{0,18}\b(?:the\s+)?(?:file|document)\b\s+(?P<p>.+)$", raw, _I)
    if m:
        path = _clean_path(m.group("p"))
        if path and not _looks_like_url(path):
            return [_action("read_file", path=path)]

    m = re.search(r"\b(?:delete|remove|erase|wipe)\b[^.]{0,18}\b(?:the\s+)?(?:file|folder|directory)\b\s+(?P<p>.+)$", raw, _I)
    if m:
        path = _clean_path(m.group("p"))
        if path:
            return [_action("delete_file", path=path)]

    m = re.search(r"\b(?:move|rename)\b\s+(?P<s>.+?)\s+to\s+(?P<d>.+)$", raw, _I)
    if m:
        src = _clean_path(m.group("s"))
        dst = _clean_path(m.group("d"))
        if src and dst:
            return [_action("move_file", path=src, destination=dst)]

    m = re.search(r"\b(?:copy|duplicate)\b\s+(?P<s>.+?)\s+to\s+(?P<d>.+)$", raw, _I)
    if m:
        src = _clean_path(m.group("s"))
        dst = _clean_path(m.group("d"))
        if src and dst:
            return [_action("copy_file", path=src, destination=dst)]

    m = re.search(r"\b(?:create|make|add)\b[^.]{0,16}\b(?:folder|directory)\b\s+(?P<p>.+)$", raw, _I)
    if m:
        path = _clean_path(m.group("p"))
        if path:
            return [_action("create_folder", path=path)]

    m = re.search(r"\b(?:list|show|browse)\b[^.]{0,18}\b(?:the\s+)?(?:files|folder|directory)\b(?:\s+(?:in|of|from)\s+(?P<p>.+))?$", raw, _I)
    if m:
        path = _clean_path(m.group("p")) if m.group("p") else ""
        return [_action("list_dir", path=path or "")]

    m = re.search(r"\b(?:search|find|locate)\b[^.]{0,12}\b(?:files?\b[^.]{0,12})?(?:named|called|matching)\s+(?P<p>\S+)(?:\s+(?:in|under|inside)\s+(?P<root>.+))?$", raw, _I)
    if m:
        pattern = m.group("p")
        root = _clean_path(m.group("root")) if m.group("root") else ""
        return [_action("search_files", target=pattern, path=root or "")]

    # ---- urls and apps ---------------------------------------------------
    m = re.search(r"\b(?:open|go to|visit|browse|navigate to|load|pull up)\b\s+(?P<u>\S+)", raw, _I)
    if m:
        url = m.group("u").strip().strip(_TRAILING)
        if _looks_like_url(url):
            return [_action("open_url", target=url)]
        if url.lower() in ("browser", "web", "internet", "google", "the browser"):
            return [_action("open_url", target="https://duckduckgo.com")]

    m = re.search(r"\b(?:google|search in browser for)\s+(?P<q>.+)$", raw, _I)
    if m:
        return [_action("open_url", target="search:" + m.group("q").strip())]

    m = re.search(r"\b(?:close|quit|exit|kill|terminate|end)\b\s+(?:the\s+)?(?P<app>[^,]+)$", raw, _I)
    if m:
        app = _clean_target(m.group("app"))
        if app and app.lower() not in _UI_TARGETS:
            return [_action("close_app", target=app)]

    m = re.search(r"\b(?:open|launch|start|run|fire up)\b\s+(?:the\s+|my\s+)?(?P<app>.+)$", raw, _I)
    if m:
        app = _clean_target(m.group("app"))
        if app and app.lower() not in _UI_TARGETS:
            return [_action("open_app", target=app)]

    return []


def spoken_intent(actions: List[Dict[str, Any]]) -> str:
    """A short sentence describing what the assistant is about to do."""
    if not actions:
        return "On it, sir."
    first = actions[0]
    args = (first.get("args") or {})
    action = str(args.get("action") or "")
    target = str(args.get("target") or args.get("path") or "")
    package = str(args.get("package") or target or "")

    if str(first.get("tool")) == "whatsapp":
        if action == "call":
            return "Calling {0} on WhatsApp, sir.".format(target)
        if action == "send_message":
            return "Sending the message on WhatsApp, sir."
        if action in ("unread_messages", "unread", "unreads"):
            return "Checking your unread WhatsApp messages, sir."
        if action in ("recent_messages", "recent", "recents"):
            return "Reading your recent WhatsApp messages, sir."
        if action in ("read_contact", "read_chat"):
            return "Checking messages from {0}, sir.".format(target)
        if action == "remember":
            return "Noted, sir."
        return "On it, sir."

    if action == "open_app":
        return "Opening {0}, sir.".format(target)
    if action == "close_app":
        return "Closing {0}, sir.".format(target)
    if action == "kill_process":
        return "Terminating {0}, sir.".format(target)
    if action == "open_url":
        return "Opening the browser, sir."
    if action == "web_fetch":
        return "Fetching that page, sir."
    if action == "web_search":
        return "Searching the web, sir."
    if action == "read_file":
        return "Reading that file, sir."
    if action == "write_file":
        return "Writing the file, sir."
    if action == "delete_file":
        return "Deleting that, sir."
    if action == "move_file":
        return "Moving the file, sir."
    if action == "copy_file":
        return "Copying the file, sir."
    if action == "list_dir":
        return "Listing the folder, sir."
    if action == "create_folder":
        return "Creating the folder, sir."
    if action == "search_files":
        return "Searching the disk, sir."
    if action == "open_file":
        return "Opening that file, sir."
    if action == "lock_screen":
        return "Locking the workstation, sir."
    if action == "shutdown":
        return "Shutting down, sir."
    if action == "restart":
        return "Restarting, sir."
    if action == "cancel_shutdown":
        return "Cancelling the shutdown, sir."
    if action == "screenshot":
        return "Taking a screenshot, sir."
    if action == "volume":
        return "Adjusting the volume, sir."
    if action == "list_processes":
        return "Listing the running processes, sir."
    if action == "kill_process":
        return "Terminating the process, sir."
    if action == "system_info":
        return "Reading the system telemetry, sir."
    if action == "bubble":
        tgt = str(args.get("target") or "toggle")
        if tgt in ("open", "show", "start", "on"):
            return "Opening the dynamic island bubble, sir."
        if tgt in ("close", "hide", "stop", "off"):
            return "Closing the bubble, sir."
        return "Toggling the dynamic island bubble, sir."
    if action == "run_command":
        return "Running that command, sir."
    if action == "install":
        return "Installing that, sir."
    if action == "install_app":
        return "Installing {0}, sir.".format(package or "that")
    if action == "uninstall_app":
        return "Uninstalling {0}, sir.".format(package or "that")
    if action == "list_installed":
        return "Listing the installed applications, sir."
    if action == "run_powershell":
        return "Running that PowerShell command, sir."
    if action == "empty_recycle_bin":
        return "Emptying the recycle bin, sir."
    if action in ("click", "screen_click", "double_click", "right_click"):
        return "Clicking {0}, sir.".format(target or "that")
    if action == "type_text":
        return "Typing that, sir."
    if action == "press_key":
        return "Pressing {0}, sir.".format(str(args.get("keys") or target or "the key").replace("+", " plus "))
    if action == "scroll":
        return "Scrolling, sir."
    if action == "move_mouse":
        return "Moving the pointer, sir."
    if action == "focus_window":
        return "Switching to {0}, sir.".format(target or "that window")
    if action == "maximize_window":
        return "Maximizing {0}, sir.".format(target or "the window")
    if action == "minimize_window":
        return "Minimizing {0}, sir.".format(target or "the window")
    if action == "restore_window":
        return "Restoring {0}, sir.".format(target or "the window")
    if action == "close_window":
        return "Closing {0}, sir.".format(target or "the window")
    if action == "list_windows":
        return "Listing the open windows, sir."
    if action == "screen":
        return "Looking at your screen, sir."
    if action == "browser":
        ba = str(args.get("browser_action") or "").lower()
        if ba in ("open_tab", "new_tab"):
            return "Opening a new tab, sir."
        if ba == "close_tab":
            return "Closing the tab, sir."
        if ba in ("close_duplicate_tabs", "close_duplicates"):
            return "Closing duplicate tabs, sir."
        if ba in ("list_tabs", "tabs"):
            return "Checking open tabs, sir."
        if ba == "switch_tab":
            return "Switching tabs, sir."
        if ba in ("reload", "refresh"):
            return "Refreshing the page, sir."
        if ba == "back":
            return "Going back, sir."
        if ba == "forward":
            return "Going forward, sir."
        return "On the browser, sir."
    if action == "workflow":
        return "Running that workflow, sir."
    if action == "send_email":
        return "Sending that email, sir."
    if action == "read_email":
        return "Checking your inbox, sir."
    if action == "calendar":
        return "Checking your calendar, sir."
    return "On it, sir."


def describe(result: Dict[str, Any]) -> str:
    """Build a spoken sentence for a result that carries no message of its own."""
    action = str(result.get("action") or "")
    if action == "list_dir":
        return "Listed {0} entries in {1}.".format(result.get("count", 0), result.get("path", ""))
    if action == "search_files":
        return "Found {0} matches for '{1}'.".format(result.get("count", 0), result.get("pattern", ""))
    if action == "list_processes":
        return "{0} processes are running.".format(result.get("count", 0))
    if action == "read_file":
        return "Read {0} bytes from {1}.".format(result.get("bytes", 0), result.get("path", ""))
    if action == "open_url":
        return "Opened {0} in the browser.".format(result.get("url", ""))
    if action == "web_fetch":
        title = result.get("title") or result.get("url", "")
        return "Fetched {0} ({1} characters of text).".format(title, result.get("chars", 0))
    if action == "web_search":
        return "{0} results for '{1}'.".format(result.get("count", 0), result.get("query", ""))
    if action == "run_command":
        code = result.get("returncode")
        output = (result.get("stdout") or "").strip().splitlines()
        tail = output[-1][:160] if output else ""
        return "Command finished (exit {0}). {1}".format(code, tail).strip()
    if action == "system_info":
        info = result.get("info") or {}
        return "System {0} {1}, {2}% memory used, {3}% of the disk used.".format(
            info.get("os", ""), info.get("release", ""),
            info.get("ram_percent", "?"), info.get("disk_percent", "?"),
        )
    if action == "clipboard":
        return "Clipboard updated."
    return "Done."


def summarise(results: List[Dict[str, Any]]) -> str:
    """Build a short spoken sentence from executed PC action results."""
    if not results:
        return ""
    ok = [r for r in results if r.get("ok")]
    bad = [r for r in results if not r.get("ok")]
    if ok:
        message = str(ok[0].get("message") or describe(ok[0]))
        if len(ok) > 1:
            message += " ({0} actions completed)".format(len(ok))
    else:
        message = "I could not do that: {0}".format(
            str(bad[0].get("error") or "unknown error")
        )
    return message


__all__ = ["detect", "summarise", "describe", "TOOL"]
