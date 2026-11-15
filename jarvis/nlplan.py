"""Turn a normal spoken sentence into desktop actions.

``pc_intents`` covers the phrasings we know word for word. This module covers
the long tail: it asks the model that is already selected (local Ollama or the
Gemini/Groq chain) to translate an imperative request into a small JSON plan of
``pc_control`` actions, validates it against the real action list, and hands it
back to the brain so the normal execution + confirmation gate runs it.

Rules that keep it safe:

* Only imperative-looking requests are planned - ordinary conversation and
  questions never reach the planner, so they cost nothing.
* Actions and argument names are whitelisted; anything unknown is dropped.
* At most :data:`MAX_ACTIONS` steps per request.
* Destructive steps are not special-cased here: ``approvals`` already parks
  delete/uninstall/shutdown/... and needs an explicit "confirm".
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.nlplan")

MAX_ACTIONS = 4

# Everything the planner is allowed to emit, with the argument names each action
# actually reads. Keeping this list explicit means a hallucinated action can
# never reach the desktop.
ACTION_ARGS: Dict[str, Tuple[str, ...]] = {
    "open_app": ("target",),
    "close_app": ("target",),
    "open_url": ("target",),
    "open_file": ("path",),
    "read_file": ("path", "limit"),
    "write_file": ("path", "content", "mode"),
    "create_folder": ("path",),
    "delete_file": ("path",),
    "move_file": ("path", "destination"),
    "copy_file": ("path", "destination"),
    "list_dir": ("path",),
    "search_files": ("path", "target", "limit"),
    "list_processes": ("limit",),
    "kill_process": ("target",),
    "list_windows": (),
    "focus_window": ("target",),
    "lock_screen": (),
    "shutdown": ("delay_seconds",),
    "restart": ("delay_seconds",),
    "cancel_shutdown": (),
    "screenshot": (),
    "system_info": (),
    "volume": ("target",),
    "type_text": ("text",),
    "press_key": ("keys",),
    "click": ("x", "y"),
    "double_click": ("x", "y"),
    "right_click": ("x", "y"),
    "scroll": ("target",),
    "clipboard": ("target", "content"),
    "run_powershell": ("command", "confirm"),
    "run_command": ("command", "confirm"),
    "install_app": ("target",),
    "uninstall_app": ("target", "confirm"),
    "list_installed": ("limit",),
    "empty_recycle_bin": ("confirm",),
    "screen": (),
    "screen_click": ("target",),
    "browser": ("browser_action", "target", "query", "url", "index"),
    "maximize_window": ("target",),
    "minimize_window": ("target",),
    "restore_window": ("target",),
    "close_window": ("target",),
    "send_email": ("to", "subject", "body", "attach"),
    "read_email": ("limit",),
    "calendar": ("limit",),
    "workflow": ("steps",),
    "bubble": ("target",),
}

CATALOG = """
open_app(target)                     launch an application, e.g. notepad, spotify
close_app(target)                    close a running application
open_url(target)                     open a web address or "search:query"
open_file(path)                      open a document with its default app
read_file(path[,limit])              read a text file
write_file(path,content)             create or overwrite a text file
create_folder(path)                  make a folder (parents included)
delete_file(path)                    DELETE a file - the user must confirm
move_file(path,destination)          move or rename
copy_file(path,destination)          copy a file
list_dir(path)                       list a folder
search_files(target[,path,limit])    find files by name
list_processes([limit])              running processes
kill_process(target)                 end a process by name or PID
list_windows()                       open windows
focus_window(target)                 bring a window to the front
maximize_window([target])            maximize active window or named app
minimize_window([target])            minimize active window or "all"
restore_window([target])             restore active window
close_window([target])               close active window or named app
lock_screen()  screenshot()  system_info()  cancel_shutdown()
shutdown([delay_seconds])  restart([delay_seconds])
volume(target)                       target is up | down | mute
type_text(text)                      type into the focused window
press_key(keys)                      e.g. "ctrl+s", "alt+tab", "enter"
click(x,y)  double_click(x,y)  right_click(x,y)  scroll(target)
clipboard(target[,content])          target is read | write
run_powershell(command)              run PowerShell - needs confirmation
install_app(target)                  winget install by id, e.g. 7zip.7zip
uninstall_app(target)                winget uninstall - needs confirmation
list_installed([limit])
screen()                             read the focused window (UIA + OCR)
screen_click(target)                 click a named control on screen
browser(browser_action[,target,url]) open | open_tab | close_tab | close_duplicate_tabs | list_tabs | reload
send_email(to,subject,body)  read_email([limit])  calendar([limit])
workflow(steps)                      list of pc_control steps
bubble(target)                       dynamic island popup: open | close | toggle
""".strip()

SYSTEM = """You convert one spoken request into Windows desktop actions for J.A.R.V.I.S.

Reply with STRICT JSON only, no prose and no markdown fences:
{"speech": "<one short spoken sentence>", "actions": [{"action": "<name>", "args": {...}}]}

Allowed actions and arguments (use the exact names):
%s

Rules:
- Use only the actions listed. Never invent an action or an argument.
- Use absolute Windows paths (C:\\Users\\... or E:\\...). Never guess a path you were not given.
- If the request is a question, chat, or anything not a desktop action, reply {"speech": "", "actions": []}.
- Keep the plan short: at most %d actions. Combine steps only when they are clearly needed.
- "speech" is what you tell the user before it runs, under 15 words.
""" % (CATALOG, MAX_ACTIONS)

# An imperative at the start of the sentence is the signal that this is a command.
_IMPERATIVE = re.compile(
    r"^\s*(?:jarvis[\s,]+)?(?:please\s+)?(?:can you|could you|would you|will you|i want you to|i need you to|go ahead and)?\s*"
    r"(?P<verb>open|launch|start|close|quit|kill|create|make|new|delete|remove|move|rename|copy|find|locate|search|list|show|read|write|save|type|press|click|scroll|install|uninstall|run|execute|set|turn|change|lock|unlock|restart|reboot|shut\s?down|email|send|schedule|add|remind|focus|switch|minimise|minimize|maximise|maximize|volume|mute|unmute|screenshot|take|play|pause)\b",
    re.IGNORECASE,
)

# "show me..." / "read this..." are usually questions about the screen, which
# pc_intents and the chat chain handle better than a blind plan.
_NOT_A_PLAN = re.compile(
    r"^\s*(?:what|why|how|who|when|where|which|is|are|do|does|did|can you tell|tell me about|explain)\b",
    re.IGNORECASE,
)

_UI_COMMANDS = re.compile(
    r"\b(?:help|commands?|settings?|options?|hud|control deck|camera mode|agents?|phone|xr|vr|ar|log|hologram|wireframe|mark 42|suit)\b",
    re.IGNORECASE,
)


def looks_actionable(text: str) -> bool:
    """True only for a request that reads like an instruction to the machine."""
    t = (text or "").strip()
    if len(t) < 3 or _NOT_A_PLAN.search(t) or _UI_COMMANDS.search(t):
        return False
    # A question mark means the user wants an answer, not a desktop action.
    if t.endswith("?") or t.endswith("."):
        return False
    match = _IMPERATIVE.match(t)
    if not match:
        return False
    # "make a joke" / "play music" style chat still reads imperative; the model
    # returns an empty plan and the normal brain answers, so no harm is done.
    return True


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    blob = text[start:end + 1]
    try:
        data = json.loads(blob)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _normalise(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw_actions = data.get("actions")
    if not isinstance(raw_actions, list):
        return None
    steps: List[Dict[str, Any]] = []
    for item in raw_actions[:MAX_ACTIONS]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("action") or item.get("name") or "").strip().lower().replace(" ", "_")
        if name not in ACTION_ARGS:
            logger.debug("planner proposed an unknown action: %r", name)
            continue
        allowed = ACTION_ARGS[name]
        # Accept both {"action": "x", "args": {...}} and flat plans.
        source = item.get("args") if isinstance(item.get("args"), dict) else {}
        merged = dict(source)
        for key, value in item.items():
            if key not in ("action", "name", "args"):
                merged.setdefault(key, value)
        args = {key: merged[key] for key in allowed if key in merged and merged[key] not in (None, "")}
        if "action" == "volume" and args.get("target"):
            args["target"] = str(args["target"]).strip().lower()
        steps.append({"tool": "pc_control", "args": {"action": name, **args}})
    if not steps:
        return None
    speech = str(data.get("speech") or "").strip()
    return {"speech": speech, "actions": steps}


def _ask_cloud(text: str) -> Optional[Tuple[str, str]]:
    """Use the same cloud providers the brain uses, honouring the Gemini switch."""
    try:
        from jarvis import settings

        gemini_on = settings.flag("gemini_enabled", True)
    except Exception:
        gemini_on = True
    if gemini_on:
        try:
            from jarvis import gemini

            answer = gemini.chat_gemini(text, system=SYSTEM, max_tokens=400, temperature=0.0)
            if answer:
                return answer, "gemini:" + (gemini.last_model() or "flash")
        except Exception as exc:
            logger.debug("gemini planning failed: %s", exc)
    try:
        from jarvis import llm

        answer = llm.chat_groq(text, system=SYSTEM, max_tokens=400, temperature=0.0)
        if answer:
            return answer, "groq:" + (llm.last_model() or "chat")
    except Exception as exc:
        logger.debug("groq planning failed: %s", exc)
    return None


def _ask_local(text: str) -> Optional[Tuple[str, str]]:
    try:
        from jarvis import ollama_local
    except Exception:
        return None
    answer = ollama_local.chat(
        text,
        system=SYSTEM,
        max_tokens=380,
        temperature=0.0,
        timeout=25.0,
    )
    if not answer:
        return None
    return answer, "local:" + ollama_local.preferred_model()


def plan(text: str) -> Optional[Dict[str, Any]]:
    """Ask the selected model for a plan. ``None`` means "not a desktop task"."""
    try:
        from jarvis import aimode, settings

        if not settings.flag("pc_control_enabled", True) or not settings.flag("brain_enabled", True):
            return None
        mode = aimode.mode()
    except Exception:
        mode = "cloud"

    asked = _ask_local(text) if mode == "local" else _ask_cloud(text)
    if not asked:
        return None
    raw, engine = asked
    data = _extract_json(raw)
    if not data:
        logger.debug("planner returned no JSON: %r", raw[:200])
        return None
    normalised = _normalise(data)
    if not normalised:
        return None
    normalised["engine"] = "planner:" + engine
    return normalised


def maybe_plan(text: str) -> Optional[Dict[str, Any]]:
    """Cheap gate first, then plan. Never raises into the chat path."""
    if not looks_actionable(text):
        return None
    try:
        return plan(text)
    except Exception as exc:
        logger.debug("planner failed: %s", exc)
        return None
