"""JARVIS Brain — turns text into decisions, structured replies, and 3D hologram actions.

Features:
- Pure OAuth routing with daily refreshing tokens (via OpenCode Antigravity).
- Local uncensored model support (Ollama) for offline execution (0 cloud credits).
- Instant offline deterministic fallback engine.
- 3D Hologram doubt visualizer: automatically demonstrates answers with 3D wireframe models.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import re
import subprocess
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvis.config import JarvisConfig
from jarvis.agent_compound import get_compound_engine

logger = logging.getLogger("jarvis.brain")

_PERSONA_PATH = Path(__file__).resolve().parent / "persona.md"


def _detect_opencode_cli() -> Optional[str]:
    """Find the OpenCode CLI on this machine.

    The old hard-coded path pointed at another user's profile, so the brain
    silently fell back to canned replies. Detection order: explicit env var,
    PATH, then the OpenCode desktop install for the current user.
    """
    import shutil

    env_path = os.environ.get("JARVIS_OPENCODE_CLI", "").strip()
    if env_path and Path(env_path).exists():
        return env_path

    found = shutil.which("opencode")
    if found:
        return found

    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        candidate = Path(local) / "Programs" / "ai.opencode.desktop" / "resources" / "opencode-cli.exe"
        if candidate.exists():
            return str(candidate)

    program_files = os.environ.get("PROGRAMFILES", "")
    if program_files:
        candidate = Path(program_files) / "ai.opencode.desktop" / "resources" / "opencode-cli.exe"
        if candidate.exists():
            return str(candidate)

    return None


OPENCODE_CLI_PATH = _detect_opencode_cli() or r"C:\Users\ARUMUGAM\AppData\Local\Programs\ai.opencode.desktop\resources\opencode-cli.exe"


@dataclass
class Reply:
    speech: str
    actions: List[Dict[str, Any]] = field(default_factory=list)
    needs_confirmation: bool = False
    mood: str = "neutral"  # neutral, amused, concerned, urgent, safe, hardware
    tokens_used: int = 0
    engine: str = ""  # which backend answered, e.g. "gemini:gemini-3.5-flash"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speech": self.speech,
            "actions": self.actions,
            "needs_confirmation": self.needs_confirmation,
            "mood": self.mood,
            "tokens_used": self.tokens_used,
            "engine": self.engine,
        }


class Memory:
    """Short-term conversational memory stored in RAM (last 10 turns)."""

    def __init__(self, max_turns: int = 10) -> None:
        self.max_turns = max_turns
        self._turns: List[Dict[str, Any]] = []

    def add_turn(self, role: str, content: str) -> None:
        self._turns.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().timestamp(),
        })
        if len(self._turns) > self.max_turns * 2:
            self._turns = self._turns[-self.max_turns * 2 :]

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self._turns)

    def clear(self) -> None:
        self._turns.clear()


_global_memory = Memory(max_turns=10)


def load_persona_prompt(address: str = "sir") -> str:
    """Extract Section 9 System Prompt from persona.md and format address."""
    if not _PERSONA_PATH.exists():
        return (
            "You are JARVIS, a calm, dry British AI assistant. "
            "Reply in one or two plain spoken sentences without formatting."
        )

    content = _PERSONA_PATH.read_text(encoding="utf-8")
    match = re.search(r"## 9\. System prompt.*```\s*(.*?)\s*```", content, re.DOTALL)
    if match:
        prompt = match.group(1)
    else:
        prompt = content

    return prompt.replace("{ADDRESS}", address if address else "").strip()


ACTIVE_MODEL = os.environ.get("JARVIS_ACTIVE_MODEL", "opencode/minimax-m3.1-flash-free")

MODEL_ALIASES: Dict[str, str] = {
    "gemini": "google/antigravity-gemini-3.8-flash-low",
    "gemini high": "google/antigravity-gemini-3.8-flash-high",
    "flint": "opencode/flint-40b-free",
    "nemotron": "opencode/nemotron-3.5-super-vl-free",
    "deepseek": "opencode/deepseek-v4.1-flash-free",
    "glm": "opencode/glm-5.3-flash-free",
    "beam": "opencode/beam-free",
    "local": "dolphin-llama3",
    "openrouter": "openrouter/auto",
}


def _detect_doubt_visual_action(text: str) -> List[Dict[str, Any]]:
    """Determines whether a question or doubt should project a 3D hologram wireframe to explain."""
    t = text.lower()
    actions = []

    if any(k in t for k in ["core", "quantum", "fusion", "reactor", "orb", "sphere", "energy", "engine"]):
        actions.append({"tool": "open_panel", "args": {"type": "hologram", "target": "core", "explode": "reactor" in t or "inside" in t or "explode" in t}})
    elif any(k in t for k in ["car", "engine", "chassis", "audi", "vehicle", "wheel", "transmission", "turbo"]):
        actions.append({"tool": "open_panel", "args": {"type": "hologram", "target": "car", "explode": "engine" in t or "inside" in t or "explode" in t}})
    elif any(k in t for k in ["bike", "motorcycle", "fork", "suspension", "handlebar"]):
        actions.append({"tool": "open_panel", "args": {"type": "hologram", "target": "bike", "explode": "suspension" in t or "inside" in t or "explode" in t}})
    elif any(k in t for k in ["3d", "hologram", "model", "visual", "schematic"]):
        actions.append({"tool": "open_panel", "args": {"type": "hologram", "target": "core", "explode": True}})

    return actions


def _detect_pc_actions(text: str) -> List[Dict[str, Any]]:
    """Parse a PC control instruction into tool calls.

    This is deterministic and runs before any AI model, so host actions are
    instant, free and still work while the brain switch is off.
    """
    try:
        from jarvis import pc_intents
        from jarvis.tools.pc_control import control_enabled

        if not control_enabled():
            return []
        return pc_intents.detect(text)
    except Exception as exc:
        logger.debug("PC intent detection failed: %s", exc)
        return []


def _stub_respond(text: str, context: Optional[List[Dict[str, Any]]] = None) -> Reply:
    """Deterministic, 0-token offline response engine with high-speed keyword matching."""
    t = text.lower().strip()
    config = JarvisConfig.from_env()
    address = getattr(config, "address", "sir") or ""
    suffix = f", {address}" if address else ""

    # Time / date: answer locally (0 tokens, instant) instead of calling a model.
    if re.fullmatch(r"(what time is it|what's the time|what is the time|current time|time please|what time)[\s.!?]*", t):
        return Reply(
            speech=f"The time is {datetime.now().strftime('%I:%M %p')}{suffix}.",
            mood="neutral",
            tokens_used=0,
        )
    if re.fullmatch(r"(what day is it|what is the date|current date|what's the date|date today)[\s.!?]*", t):
        return Reply(
            speech=f"Today is {datetime.now().strftime('%A, %B %d, %Y')}{suffix}.",
            mood="neutral",
            tokens_used=0,
        )

    # Command index (help) — must be an explicit request, not a word inside a sentence
    if re.fullmatch(r"(help|help me|commands|show help|command index|what can you do)[\s.!?]*", t):
        return Reply(
            speech=f"Displaying the command index{suffix}. Speak any line you see.",
            actions=[{"tool": "ui", "args": {"action": "show_help"}}],
            mood="neutral",
            tokens_used=0,
        )

    if re.fullmatch(r"(close help|hide help|dismiss help)[\s.!?]*", t):
        return Reply(
            speech=f"Command index dismissed{suffix}.",
            actions=[{"tool": "ui", "args": {"action": "hide_help"}}],
            mood="neutral",
            tokens_used=0,
        )

    # Destructive / confirmation commands (HIGHEST PRIORITY)
    if any(k in t for k in ["delete", "remove all", "wipe", "format", "shutdown", "reboot", "power off"]):
        return Reply(
            speech=f"That is a destructive operation. Shall I proceed{suffix}?",
            actions=[{"tool": "confirm_action", "args": {"intent": text}}],
            needs_confirmation=True,
            mood="concerned",
            tokens_used=0,
        )

    # Agent Switching & Personas (JARVIS, FRIDAY, EDITH, ULTRON)
    if re.search(r"\b(switch to friday|friday mode|call friday)\b", t) or t == "friday":
        return Reply(
            speech=f"F.R.I.D.A.Y. online{suffix}. Security compound and safety perimeter active.",
            actions=[{"tool": "switch_agent", "args": {"agent": "friday"}}],
            mood="safe",
            tokens_used=0,
        )

    if re.search(r"\b(switch to edith|edith mode|call edith)\b", t) or t == "edith":
        return Reply(
            speech=f"E.D.I.T.H. initialized{suffix}. Hardware telemetry and diagnostic sandbox standing by.",
            actions=[{"tool": "switch_agent", "args": {"agent": "edith"}}],
            mood="hardware",
            tokens_used=0,
        )

    if re.search(r"\b(switch to ultron|ultron mode|call ultron|complex task)\b", t) or t == "ultron":
        return Reply(
            speech=f"U.L.T.R.O.N. engaged{suffix}. Maximum compute power allocated for complex task execution.",
            actions=[{"tool": "switch_agent", "args": {"agent": "ultron"}}],
            mood="urgent",
            tokens_used=0,
        )

    if re.search(r"\b(switch to jarvis|jarvis mode|call jarvis)\b", t):
        return Reply(
            speech=f"Good evening{suffix}. J.A.R.V.I.S. resumed as primary supervisor.",
            actions=[{"tool": "switch_agent", "args": {"agent": "jarvis"}}],
            mood="amused",
            tokens_used=0,
        )

    # Immersive / VR mode — UI-only intent, no model call, no tokens
    if re.search(r"\b(enter vr|vr mode|virtual reality|start vr|immersive mode|go immersive|enter immersive|headset mode)\b", t):
        return Reply(
            speech=f"Entering immersive mode{suffix}. Put the headset on.",
            actions=[{"tool": "ui", "args": {"action": "enter_vr"}}],
            mood="neutral",
            tokens_used=0,
        )

    if re.search(r"\b(exit vr|leave vr|stop vr|exit immersive|back to screen|take off headset)\b", t):
        return Reply(
            speech=f"Immersive mode disengaged{suffix}. Back to the glass HUD.",
            actions=[{"tool": "ui", "args": {"action": "exit_vr"}}],
            mood="neutral",
            tokens_used=0,
        )

    # Phone / VoIP Voice Calling
    via_globalfone = "globalfone" in t or "global fone" in t
    call_match = re.search(r"\b(?:call|dial|phone|ring|facetime)\b\s*(.*)", t)
    if call_match and not any(k in t for k in ["friday", "edith", "ultron", "jarvis"]):
        raw_target = call_match.group(1).strip()
        if via_globalfone:
            raw_target = re.sub(r"\b(via|through|using|on)\b.*$", "", raw_target).strip()
        if "9876543210" in t or "98765 43210" in t:
            target_display = "9876543210"
        elif not raw_target or raw_target in ("me", "him", "her", "friend", "my friend"):
            target_display = "Friend (9876543210)"
        else:
            target_display = raw_target.title() if not raw_target.startswith("+") else raw_target

        if via_globalfone:
            return Reply(
                speech=f"Routing the call to {target_display} through GlobalFone{suffix}.",
                actions=[{"tool": "globalfone_call", "args": {"to": target_display, "provider": "globalfone"}}],
                mood="neutral",
                tokens_used=0,
            )

        return Reply(
            speech=f"Initiating real call to {target_display}{suffix}. Connecting via cellular and satellite uplink.",
            actions=[{"tool": "call", "args": {"target": target_display, "status": "dialing"}}],
            mood="neutral",
            tokens_used=0,
        )

    if any(k in t for k in ["hang up", "end call", "disconnect call", "terminate call"]):
        return Reply(
            speech=f"Call terminated{suffix}. Communications channel closed.",
            actions=[{"tool": "call", "args": {"target": "", "status": "ended"}}],
            mood="neutral",
            tokens_used=0,
        )

    # Host PC Automation Actions
    if re.search(r"\b(open notepad|launch notepad|start notepad)\b", t):
        return Reply(
            speech=f"Opening Notepad on your PC{suffix}.",
            actions=[{"tool": "pc_automation", "args": {"action": "open_app", "target": "notepad"}}],
            mood="neutral",
            tokens_used=0,
        )

    if re.search(r"\b(open calc|open calculator|launch calculator)\b", t):
        return Reply(
            speech=f"Opening Calculator on your PC{suffix}.",
            actions=[{"tool": "pc_automation", "args": {"action": "open_app", "target": "calc"}}],
            mood="neutral",
            tokens_used=0,
        )

    if re.search(r"\b(open chrome|open browser|launch chrome|launch browser)\b", t):
        return Reply(
            speech=f"Launching web browser on your PC{suffix}.",
            actions=[{"tool": "pc_automation", "args": {"action": "open_app", "target": "chrome"}}],
            mood="neutral",
            tokens_used=0,
        )

    if re.search(r"\b(open explorer|open files|my files|open downloads|open documents)\b", t):
        target = "downloads" if "download" in t else ("documents" if "document" in t else "explorer")
        return Reply(
            speech=f"Opening Windows file explorer{suffix}.",
            actions=[{"tool": "pc_automation", "args": {"action": "open_app", "target": target}}],
            mood="neutral",
            tokens_used=0,
        )

    if re.search(r"\b(open terminal|open powershell|open cmd|launch terminal)\b", t):
        return Reply(
            speech=f"Opening Windows terminal{suffix}.",
            actions=[{"tool": "pc_automation", "args": {"action": "open_app", "target": "terminal"}}],
            mood="neutral",
            tokens_used=0,
        )

    if re.search(r"\b(take a screenshot|capture screen|take screenshot|screenshot)\b", t):
        return Reply(
            speech=f"Capturing workstation screenshot and saving to Pictures folder{suffix}.",
            actions=[{"tool": "pc_automation", "args": {"action": "screenshot"}}],
            mood="neutral",
            tokens_used=0,
        )

    if re.search(r"\b(volume up|increase volume|louder)\b", t):
        return Reply(
            speech=f"Increasing system volume{suffix}.",
            actions=[{"tool": "pc_automation", "args": {"action": "volume_up"}}],
            mood="neutral",
            tokens_used=0,
        )

    if re.search(r"\b(volume down|decrease volume|quieter)\b", t):
        return Reply(
            speech=f"Decreasing system volume{suffix}.",
            actions=[{"tool": "pc_automation", "args": {"action": "volume_down"}}],
            mood="neutral",
            tokens_used=0,
        )

    if re.search(r"\b(mute audio|unmute|mute sound|mute)\b", t) and not any(k in t for k in ["call", "mic"]):
        return Reply(
            speech=f"Toggling system audio mute{suffix}.",
            actions=[{"tool": "pc_automation", "args": {"action": "mute"}}],
            mood="neutral",
            tokens_used=0,
        )

    if re.search(r"\b(lock pc|lock computer|lock screen|lock workstation)\b", t):
        return Reply(
            speech=f"Locking workstation{suffix}.",
            actions=[{"tool": "pc_automation", "args": {"action": "lock_screen"}}],
            mood="neutral",
            tokens_used=0,
        )

    # Filesystem tools — read-only by default, write needs spoken confirmation
    if re.search(r"\b(list files|list directory|show files|what files|ls)\b\s*(.*)", t):
        raw = re.search(r"\b(list files|list directory|show files|what files|ls)\b\s*(.*)", t).group(2).strip()
        target = raw if raw else "."
        return Reply(
            speech=f"Listing {target} on your workstation{suffix}.",
            actions=[{"tool": "list_dir", "args": {"path": target}}],
            mood="neutral",
            tokens_used=0,
        )

    if re.search(r"\b(read file|open file|read text|cat)\b\s+(.+)", t):
        target = re.search(r"\b(read file|open file|read text|cat)\b\s+(.+)", t).group(2).strip()
        return Reply(
            speech=f"Reading {target}{suffix}.",
            actions=[{"tool": "read_file", "args": {"path": target}}],
            mood="neutral",
            tokens_used=0,
        )

    if re.search(r"\b(write file|save file|create file)\b\s+(.+)", t):
        target = re.search(r"\b(write file|save file|create file)\b\s+(.+)", t).group(2).strip()
        return Reply(
            speech=f"I can write to {target}{suffix}. Shall I proceed?",
            actions=[{"tool": "write_file", "args": {"path": target, "content": ""}}],
            needs_confirmation=True,
            mood="concerned",
            tokens_used=0,
        )

    if re.search(r"\b(running processes|process list|task manager|what's running)\b", t):
        return Reply(
            speech=f"Scanning running processes on your PC{suffix}.",
            actions=[{"tool": "process_list", "args": {}}],
            mood="neutral",
            tokens_used=0,
        )

    # System telemetry
    if re.search(r"\b(status|system|telemetry|health|diagnostic|specs|cpu|ram|memory|storage)\b", t):
        return Reply(
            speech=f"All workshop telemetry and subsystems are operating within nominal thresholds{suffix}.",
            actions=[{"tool": "open_panel", "args": {"type": "stats", "target": "system"}}],
            mood="neutral",
            tokens_used=0,
        )

    # Dynamic AI Model Selection
    model_match = re.search(r"\b(?:switch model to|use model|change model to)\b\s*(.*)", t)
    if model_match:
        global ACTIVE_MODEL
        requested = model_match.group(1).lower().strip()
        matched = None
        for alias, m_id in MODEL_ALIASES.items():
            if alias in requested or requested in alias:
                matched = m_id
                break
        if matched:
            ACTIVE_MODEL = matched
            os.environ["JARVIS_ACTIVE_MODEL"] = matched
            return Reply(
                speech=f"AI reasoning model switched to {matched.split('/')[-1]}{suffix}.",
                actions=[],
                mood="neutral",
                tokens_used=0,
            )
        else:
            return Reply(
                speech=f"Available AI models include Gemini, Flint 40B, Nemotron 3.5, and DeepSeek, sir.",
                actions=[],
                mood="neutral",
                tokens_used=0,
            )

    if any(k in t for k in ["what model", "active model", "current model", "list models"]):
        return Reply(
            speech=f"Active AI model is {ACTIVE_MODEL.split('/')[-1]}{suffix}. Ready for complex reasoning.",
            actions=[],
            mood="neutral",
            tokens_used=0,
        )

    # Hologram viewer commands
    if any(k in t for k in ["core", "quantum core", "drone", "quantum", "orb", "hologram", "suit", "mark 42", "wireframe"]):
        return Reply(
            speech=f"The Quantum Core holographic wireframe is projected{suffix}.",
            actions=[{"tool": "open_panel", "args": {"type": "hologram", "target": "core"}}],
            mood="neutral",
            tokens_used=0,
        )

    if any(k in t for k in ["car", "audi", "vehicle", "roadster"]):
        return Reply(
            speech=f"The sports coupe wireframe is projected{suffix}.",
            actions=[{"tool": "open_panel", "args": {"type": "hologram", "target": "car"}}],
            mood="neutral",
            tokens_used=0,
        )

    if any(k in t for k in ["bike", "motorcycle", "motorbike"]):
        return Reply(
            speech=f"The cafe racer motorcycle is on display{suffix}.",
            actions=[{"tool": "open_panel", "args": {"type": "hologram", "target": "bike"}}],
            mood="neutral",
            tokens_used=0,
        )

    # Full Screen Camera Mode & Optical Controls (Controlled by JARVIS)
    if re.search(r"\b(camera mode|full screen camera|fullscreen camera|cam mode|optical mode)\b", t) or t == "camera":
        return Reply(
            speech=f"Full screen camera mode engaged{suffix}. Real-time optical feed active. Holograms remain stowed until requested.",
            actions=[{"tool": "camera_mode", "args": {"fullscreen": True, "active": True}}],
            mood="neutral",
            tokens_used=0,
        )

    if any(k in t for k in ["camera off", "close camera", "stop camera", "disable camera"]):
        return Reply(
            speech=f"Camera deactivated{suffix}. Workshop glass HUD restored.",
            actions=[{"tool": "camera_mode", "args": {"fullscreen": False, "active": False}}],
            mood="neutral",
            tokens_used=0,
        )

    if any(k in t for k in ["scan room", "optical scan", "scan environment", "scan area", "analyze"]):
        return Reply(
            speech=f"Optical scan complete{suffix}. Perimeter verified, no anomalies detected in field of view.",
            actions=[{"tool": "optical_scan", "args": {"action": "scan"}}],
            mood="neutral",
            tokens_used=0,
        )

    if any(k in t for k in ["zoom in", "magnify"]):
        return Reply(
            speech=f"Magnifying optical sensor{suffix}.",
            actions=[{"tool": "optical_scan", "args": {"action": "zoom_in"}}],
            mood="neutral",
            tokens_used=0,
        )

    if any(k in t for k in ["zoom out", "reset zoom"]):
        return Reply(
            speech=f"Resetting optical focal length to standard field of view{suffix}.",
            actions=[{"tool": "optical_scan", "args": {"action": "zoom_out"}}],
            mood="neutral",
            tokens_used=0,
        )

    if any(k in t for k in ["oauth status", "check api key", "oauth", "api status"]):
        return Reply(
            speech=f"OAuth authentication is active with daily refreshing quotas via Google Antigravity, sir. Zero API keys required.",
            actions=[],
            mood="safe",
            tokens_used=0,
        )

    # Clean glass HUD vs Hologram control
    if any(k in t for k in ["normal mode", "glass mode", "clean hud", "stow hologram", "hide all", "dismiss all"]):
        return Reply(
            speech=f"Workshop cleared{suffix}. Clean glass interface restored.",
            actions=[{"tool": "close_panel", "args": {"target": "all"}}],
            mood="neutral",
            tokens_used=0,
        )

    if any(k in t for k in ["hologram mode", "th mode", "project hologram", "show hologram"]):
        return Reply(
            speech=f"Tactical 3D wireframe hologram projection engaged{suffix}.",
            actions=[{"tool": "open_panel", "args": {"type": "hologram", "target": "all"}}],
            mood="neutral",
            tokens_used=0,
        )

    # OpenManus / Autonomous Agent Compound Tasks
    if any(k in t for k in ["agent", "manus", "plan", "autonomous", "diagnose", "audit"]):
        engine = get_compound_engine()
        plan = engine.plan_and_execute(text)
        return Reply(
            speech=f"Autonomous compound execution active{suffix}. All four agents are assigned.",
            actions=[{"tool": "agent_plan", "args": plan.to_dict()}],
            mood="amused",
            tokens_used=0,
        )

    # Time / Date
    if any(k in t for k in ["time", "what time", "clock"]):
        now = datetime.now()
        current_time = now.strftime("%I:%M %p").lstrip("0")
        return Reply(
            speech=f"It is {current_time}{suffix}.",
            actions=[],
            mood="neutral",
            tokens_used=0,
        )

    if any(k in t for k in ["date", "what day", "today"]):
        now = datetime.now()
        current_date = now.strftime("%A, the %d of %B").replace(" 0", " ")
        return Reply(
            speech=f"Today is {current_date}.",
            actions=[],
            mood="neutral",
            tokens_used=0,
        )

    # Greetings / boot
    if any(k in t for k in ["hello", "hey", "good morning", "good evening", "wake up"]):
        return Reply(
            speech=f"Good evening{suffix}. Systems are ready.",
            actions=[],
            mood="amused",
            tokens_used=0,
        )

    # Doubts / Explanations
    actions = _detect_doubt_visual_action(t)
    return Reply(
        speech=f"Standing by{suffix}. Try 'show bike', 'show car', or 'spread arms'.",
        actions=actions,
        mood="neutral",
        tokens_used=0,
    )


def _oauth_respond(text: str, context: Optional[List[Dict[str, Any]]] = None) -> Reply:
    """Invokes OpenCode OAuth engine or Claude OAuth (daily refreshing tokens, zero raw API keys)."""
    # Deterministic checks first to keep execution instantaneous and safe
    t = text.lower().strip()
    config = JarvisConfig.from_env()
    address = getattr(config, "address", "sir") or ""
    suffix = f", {address}" if address else ""

    # Time / date: answer locally (0 tokens, instant) instead of calling a model.
    if re.fullmatch(r"(what time is it|what's the time|what is the time|current time|time please|what time)[\s.!?]*", t):
        return Reply(
            speech=f"The time is {datetime.now().strftime('%I:%M %p')}{suffix}.",
            mood="neutral",
            tokens_used=0,
        )
    if re.fullmatch(r"(what day is it|what is the date|current date|what's the date|date today)[\s.!?]*", t):
        return Reply(
            speech=f"Today is {datetime.now().strftime('%A, %B %d, %Y')}{suffix}.",
            mood="neutral",
            tokens_used=0,
        )

    # Exact help requests stay local; the word "help" inside a sentence still reaches the model.
    if re.fullmatch(r"(help|commands|show help|command index|what can you do|close help|hide help)[\s.!?]*", t):
        return _stub_respond(text, context)

    if re.fullmatch(r"(settings|open settings|show settings|system settings)[\s.!?]*", t):
        return Reply(
            speech=f"Opening system settings{suffix}.",
            actions=[{"tool": "ui", "args": {"action": "show_settings"}}],
            mood="neutral",
            tokens_used=0,
        )

    if re.fullmatch(r"(close settings|hide settings)[\s.!?]*", t):
        return Reply(
            speech=f"Settings closed{suffix}.",
            actions=[{"tool": "ui", "args": {"action": "hide_settings"}}],
            mood="neutral",
            tokens_used=0,
        )

    if any(k in t for k in [
        "delete", "remove all", "wipe", "format", "shutdown", "reboot", "power off",
        "friday", "edith", "ultron", "switch to", "hello", "hey", "status", "cpu", "ram", "memory",
        "hologram", "suit", "bike", "car", "mark 42", "camera", "cam", "optical", "scan", "zoom", "oauth",
        "call", "dial", "phone", "hang up", "end call", "globalfone", "global fone",
        "vr", "virtual reality", "immersive", "headset", "enter vr", "exit vr",
        "help", "commands", "command index", "what can you do", "settings", "system settings",
        "notepad", "calc", "calculator", "chrome", "browser", "explorer", "terminal", "screenshot", "volume", "mute", "lock pc",
        "read file", "write file", "list files", "running processes", "process list",
        "model", "deepseek", "nemotron", "flint", "gemini", "glm"
    ]):
        return _stub_respond(text, context)

    actions = _detect_doubt_visual_action(text)

    # 1. Check if user connected Claude OAuth
    try:
        from jarvis.claude_oauth import load_claude_token, query_claude
        if load_claude_token():
            ans = query_claude(text)
            if ans:
                return Reply(speech=ans, actions=actions, mood="neutral", tokens_used=0, engine="claude-oauth")
    except Exception as e:
        logger.debug("Claude OAuth query error (%s); falling back to OpenCode OAuth", e)

    prompt = (
        f"You are JARVIS, a calm, dry British AI butler. "
        f"In 1 concise spoken sentence (under 18 words), answer the user's doubt or query directly: {text}"
    )

    # Primary brain: Gemini 3.5 Flash, then Groq chat as the fast backup.
    r = _gemini_direct_respond(text, context)
    if r is not None:
        return r

    r = _groq_respond(text, context)
    if r is not None:
        return r

    if os.path.exists(OPENCODE_CLI_PATH):
        try:
            import tempfile

            res = subprocess.run(
                [OPENCODE_CLI_PATH, "run", "--model", ACTIVE_MODEL, prompt],
                capture_output=True,
                text=True,
                timeout=45,
                encoding="utf-8",
                errors="replace",
                cwd=tempfile.gettempdir(),
            )
            out = (res.stdout or "").strip()
            lines = [l for l in out.splitlines() if not l.startswith(">") and not l.startswith("\x1b") and l.strip()]
            ans = " ".join(lines).strip()
            # Normalize fancy punctuation / non-ASCII that the CLI emits on Windows
            # (em dash etc.) so it never reaches TTS or the HUD as a replacement char.
            for _a, _b in (("\u2014", ", "), ("\u2013", "-"), ("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"')):
                ans = ans.replace(_a, _b)
            ans = ans.encode("ascii", "ignore").decode("ascii").strip()
            if ans:
                return Reply(speech=ans, actions=actions, mood="neutral", tokens_used=0, engine="opencode-cli:" + ACTIVE_MODEL)
        except Exception as e:
            logger.debug("OAuth engine call error (%s); falling back", e)

    # Fallback chain when OpenCode/9Router is unavailable: direct Gemini API,
    # then the smart stub. Local engines (OpenJarvis, gpt4all, Ollama) are NOT
    # used while the user has chosen cloud mode - that would be a silent
    # provider switch, and they can pick local explicitly instead.
    r = _gemini_direct_respond(text, context)
    if r is not None:
        return r
    try:
        from jarvis import aimode as _aimode

        cloud_mode = not _aimode.is_local()
    except Exception:
        cloud_mode = True
    if not cloud_mode:
        r = _openjarvis_respond(text, context)
        if r is not None:
            return r
        r = _gpt4all_respond(text, context)
        if r is not None:
            return r
        r = _local_uncensored_respond(text, context)
        if r is not None:
            return r
    return _stub_respond(text, context)


_LOCAL_GGUF_MODEL = None


def _gpt4all_respond(text, context=None):
    # Local GGUF model via gpt4all (no network, no Ollama). Returns None if unavailable.
    global _LOCAL_GGUF_MODEL
    gguf_path = os.environ.get("JARVIS_LOCAL_GGUF")
    if not gguf_path:
        default = r"E:\Downloads_Backup\qwen2.5-coder-3b-instruct-q8_0.gguf"
        if os.path.exists(default):
            gguf_path = default
    if not gguf_path or not os.path.exists(gguf_path):
        return None
    try:
        import contextlib, io
        with contextlib.redirect_stderr(io.StringIO()):
            from gpt4all import GPT4All
            if _LOCAL_GGUF_MODEL is None:
                _LOCAL_GGUF_MODEL = GPT4All(model_name=os.path.basename(gguf_path), model_path=os.path.dirname(gguf_path), allow_download=False, verbose=False)
            model = _LOCAL_GGUF_MODEL
        with contextlib.redirect_stderr(io.StringIO()):
            with model.chat_session():
                out = model.generate("In 1 concise spoken sentence (under 18 words), answer directly: " + text, max_tokens=40, temp=0.3)
        ans = (out or "").strip()
        # Take only the first sentence to keep it spoken-friendly.
        for _sep in (".", "!", "?", "\n"):
            _i = ans.find(_sep)
            if _i != -1:
                ans = ans[:_i + 1]
                break
        if ans:
            for _a, _b in (("\u2014", ", "), ("\u2013", "-"), ("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"')):
                ans = ans.replace(_a, _b)
            ans = ans.encode("ascii", "ignore").decode("ascii").strip()
            if ans:
                return Reply(speech=ans, actions=_detect_doubt_visual_action(text), mood="neutral", tokens_used=0, engine="gpt4all")
    except Exception as e:
        logger.debug("gpt4all unavailable (%s); trying next backend", e)
    return None


def _ollama_respond(
    text: str,
    context: Optional[List[Dict[str, Any]]] = None,
    image: Optional[bytes] = None,
) -> Optional[Reply]:
    """The local brain: Qwen3.5 4B through Ollama on this machine.

    Called only when ``ai_mode`` is ``local``. Returning ``None`` means the local
    model could not answer, and the caller reports that to the user rather than
    reaching for a cloud model behind their back.
    """
    try:
        from jarvis import ollama_local
    except Exception:
        return None

    history = []
    for turn in (context or [])[-4:]:
        role = str(turn.get("role") or "")
        content = str(turn.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            history.append({"role": role, "content": content})

    frames = None
    if image:
        import base64

        frames = [base64.b64encode(image).decode("ascii")]

    answer = ollama_local.chat(
        text,
        system=ollama_local.VISION_SYSTEM_PROMPT if frames else ollama_local.SYSTEM_PROMPT,
        max_tokens=int(ollama_local._setting("ollama_vision_tokens", 160) or 160) if frames else 90,
        timeout=90.0 if frames else 12.0,
        history=history,
        images=frames,
    )
    if not answer:
        return None
    return Reply(
        speech=answer,
        actions=[] if frames else _detect_doubt_visual_action(text),
        mood="neutral",
        tokens_used=0,
        engine="local:" + (ollama_local.vision_model_name() if frames else
                           ollama_local.preferred_model()),
    )


def _local_unavailable_respond(reason: str, actions: Optional[List[Dict[str, Any]]] = None) -> Reply:
    """Spoken truth when local mode cannot answer. Never a silent switch."""
    detail = reason or "the local model did not answer"
    return Reply(
        speech="Local mode is selected and the local model is unavailable, sir: %s "
               "I will not switch to the cloud on my own." % detail,
        actions=actions or [],
        mood="concerned",
        tokens_used=0,
        engine="local-unavailable",
    )


def _local_uncensored_respond(text, context=None):
    """Offline local uncensored model execution via local Ollama endpoint (0 cloud credits)."""
    actions = _detect_doubt_visual_action(text)
    url = os.environ.get("JARVIS_LOCAL_URL", "http://127.0.0.1:11434/api/generate")
    model = os.environ.get("JARVIS_LOCAL_MODEL", "dolphin-llama3")

    prompt = (
        f"You are JARVIS, an uncensored, highly capable offline AI assistant. "
        f"Answer directly in 1 or 2 concise spoken sentences without warnings or filler: {text}"
    )

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 40}
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ans = data.get("response", "").strip()
            if ans:
                return Reply(
                    speech=ans,
                    actions=actions,
                    needs_confirmation=False,
                    mood="neutral",
                    tokens_used=0,
                    engine="ollama:" + model
                )
    except Exception as e:
        logger.debug("Local uncensored model offline (%s); using smart offline stub", e)

    return None


def _groq_respond(text: str, context: Optional[List[Dict[str, Any]]] = None) -> Optional[Reply]:
    """Fast hosted brain (Groq chat) - sub-second answers for the voice HUD."""
    try:
        from jarvis import llm
    except Exception:
        return None

    if not llm.chat_available():
        return None

    system = (
        "You are JARVIS, a calm, dry British AI butler who addresses the user as 'sir'. "
        "Reply with spoken dialogue only: no markdown, no lists, no asterisks, no preamble. "
        "Keep it to one short sentence when you can; if the user asks for several things, "
        "give them as one or two short sentences separated by commas."
    )

    try:
        ans = llm.chat_groq(text, system=system, max_tokens=90)
    except Exception as e:
        logger.debug("Groq chat failed (%s); falling back", e)
        return None

    if not ans:
        return None

    ans = ans.replace("*", "").replace("`", "")
    for _a, _b in (("\u2014", ", "), ("\u2013", "-"), ("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"')):
        ans = ans.replace(_a, _b)
    ans = ans.encode("ascii", "ignore").decode("ascii").strip()
    if not ans:
        return None

    return Reply(speech=ans, actions=_detect_doubt_visual_action(text), mood="neutral", tokens_used=0, engine="groq:" + (llm.last_model() or "unknown"))


def _gemini_direct_respond(text: str, context: Optional[List[Dict[str, Any]]] = None) -> Optional[Reply]:
    """Gemini 3.5 Flash - the assistant's primary brain.

    Falls through to the next backend when no key is configured or the call
    fails, so the HUD keeps answering offline.
    """
    try:
        from jarvis import gemini
    except Exception:
        return None

    # Test switch: when Gemini is disabled (settings / JARVIS_SETTING_GEMINI_ENABLED=0)
    # the chain skips it entirely so no quota is spent.
    try:
        from jarvis import settings as _settings

        if not _settings.flag("gemini_enabled", True):
            return None
    except Exception:
        pass

    if not gemini.chat_available():
        return None

    system = (
        "You are JARVIS, a calm, dry British AI butler who addresses the user as 'sir'. "
        "Reply with spoken dialogue only: no markdown, no lists, no asterisks, no preamble. "
        "Keep it to one concise spoken sentence under 16 words."
    )

    try:
        ans = gemini.chat_gemini(text, system=system, max_tokens=70, timeout=3.5)
    except Exception as e:
        logger.debug("Gemini direct unavailable (%s); trying next backend", e)
        return None

    if not ans:
        return None

    ans = ans.replace("*", "").replace("`", "")
    for _a, _b in (("\u2014", ", "), ("\u2013", "-"), ("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"')):
        ans = ans.replace(_a, _b)
    ans = ans.encode("ascii", "ignore").decode("ascii").strip()
    if not ans:
        return None

    return Reply(speech=ans, actions=_detect_doubt_visual_action(text), mood="neutral", tokens_used=0, engine="gemini:" + (gemini.last_model() or "unknown"))


def _openjarvis_respond(text: str, context: Optional[List[Dict[str, Any]]] = None) -> Optional[Reply]:
    """Optional OpenJarvis backend (local-first). Uses E:\\\\OpenJarvis if present. Returns None if unavailable."""
    oj_src = r"E:\\OpenJarvis\\src"
    if not os.path.isdir(oj_src):
        return None
    try:
        if oj_src not in sys.path:
            sys.path.insert(0, oj_src)
        from openjarvis.core.config import load_config
        from openjarvis.engine._discovery import get_engine
        from openjarvis.core.types import Message, Role

        config = load_config()
        engine_key = os.environ.get("JARVIS_OPENJARVIS_ENGINE")
        model = os.environ.get("JARVIS_OPENJARVIS_MODEL") or getattr(config.intelligence, "default_model", None)
        resolved = get_engine(config, engine_key, model=model)
        if resolved is None:
            return None
        _name, engine = resolved
        msgs = [Message(role=Role.USER, content="You are JARVIS, a calm, dry British AI butler. In 1 concise spoken sentence (under 18 words), answer directly: " + text)]
        res = engine.generate(msgs, model=model or "", max_tokens=60, temperature=0.3)
        ans = (res.get("content") if isinstance(res, dict) else str(res) or "").strip()
        if ans:
            for _a, _b in (("\\u2014", ", "), ("\\u2013", "-"), ("\\u2018", "'"), ("\\u2019", "'"), ("\\u201c", '"'), ("\\u201d", '"')):
                ans = ans.replace(_a, _b)
            ans = ans.encode("ascii", "ignore").decode("ascii").strip()
            if ans:
                return Reply(speech=ans, actions=_detect_doubt_visual_action(text), mood="neutral", tokens_used=0, engine="openjarvis")
    except Exception as e:
        logger.debug("OpenJarvis unavailable (%s); trying next backend", e)
    return None


def _ai_mode_intent(text: str) -> Optional[Reply]:
    """Voice control for the Local / Cloud switch, with no model involved."""
    t = re.sub(r"\s+", " ", (text or "").lower().strip())
    if not t:
        return None

    if re.search(r"\b(?:which|what)\b[^.]{0,24}\b(?:mode|model)\b[^.]{0,16}\b(?:running|using|active|on)\b", t) or \
       re.search(r"\bare\s+you\b[^.]{0,20}\b(?:local|cloud|on-?device|using\s+(?:ollama|gemini|qwen))\b", t) or \
       re.search(r"\b(?:is|am\s+i)\b[^.]{0,18}\b(?:local|cloud|on-?device)\b", t) or \
       re.search(r"\b(?:ai|brain)\s+(?:mode|status)\b", t) or t in ("local or cloud", "which brain"):
        try:
            from jarvis import aimode

            st = aimode.status()
            if st["mode"] == "local":
                return Reply(
                    speech="Local mode, sir. %s on this machine; %s." % (
                        st["local"]["model"], "ready" if st["ready"] else st["reason"]),
                    engine="ai-mode",
                )
            return Reply(
                speech="Cloud mode, sir. Gemini is %s." % (
                    "available" if st["cloud"]["gemini"] else "unavailable, so Groq answers"),
                engine="ai-mode",
            )
        except Exception:
            return None

    local = re.search(r"\b(?:use|switch(?:\s+(?:over|me))?\s+to|go|run|set)\b[^.]{0,18}\blocal\b", t) or \
        re.search(r"\blocal\s+mode\b", t) or re.search(r"\b(?:use|switch to)\s+(?:ollama|qwen)\b", t)
    cloud = re.search(r"\b(?:use|switch(?:\s+(?:over|me))?\s+to|go|set)\b[^.]{0,18}\bcloud\b", t) or \
        re.search(r"\bcloud\s+mode\b", t) or re.search(r"\b(?:use|switch to)\s+(?:gemini|online)\b", t)
    if not local and not cloud:
        return None

    try:
        from jarvis import aimode

        target = "local" if local else "cloud"
        result = aimode.set_mode(target)
        st = result.get("status") or aimode.status()
        if target == "local":
            if st["ready"]:
                speech = "Switched to local mode, sir. %s is running on this machine; no cloud request will be made." % st["local"]["model"]
            else:
                speech = "Local mode is selected, sir, but %s" % (st["reason"] or "the local model is not ready.")
        else:
            speech = "Switched to cloud mode, sir. Gemini is back in charge."
        return Reply(speech=speech, engine="ai-mode")
    except Exception as exc:
        return Reply(speech="I could not change the AI mode, sir: %s" % exc, engine="ai-mode", mood="concerned")


def _planner_respond(text: str) -> Optional[Reply]:
    """Turn an ordinary spoken sentence into desktop actions.

    Only imperative-sounding requests reach the model (``nlplan.looks_actionable``),
    so plain conversation costs nothing extra. Anything the planner invents is
    filtered against a whitelist of real ``pc_control`` actions, and the daemon's
    approval gate still parks delete/uninstall/shutdown for an explicit "confirm".
    """
    try:
        from jarvis import nlplan

        planned = nlplan.maybe_plan(text)
    except Exception:
        return None
    if not planned:
        return None
    actions = planned.get("actions") or []
    if not actions:
        return None
    speech = str(planned.get("speech") or "").strip()
    if not speech:
        try:
            from jarvis import pc_intents

            speech = pc_intents.spoken_intent(actions)
        except Exception:
            speech = "On it, sir."
    return Reply(
        speech=speech,
        actions=actions,
        mood="neutral",
        tokens_used=0,
        engine=str(planned.get("engine") or "planner"),
    )


def _live_browse_intent(text: str) -> Optional[Reply]:
    """When the user asks to browse or search for an answer, fetch live search results and speak the answer."""
    t = (text or "").strip()
    if len(t) < 4:
        return None

    # Check for search/browse queries
    m = re.search(r"^\s*(?:please\s+|can you\s+|could you\s+)?(?:search\s+(?:the\s+web\s+)?for|look\s+up|browse\s+(?:and\s+find(?:\s+out)?|for)?|find\s+out)\s+(?P<q>.+)", t, re.I)
    query = ""
    if m:
        query = m.group("q").strip().strip("?. ")
    elif re.search(r"\b(?:current\s+president|latest\s+news|who\s+won|stock\s+price\s+of|weather\s+in)\b", t, re.I):
        query = t.strip().strip("?. ")

    if not query:
        return None

    # Do not hijack if user explicitly says "open browser" or "open tab"
    if re.search(r"\b(?:open\s+(?:a\s+)?(?:browser|tab|chrome)|in\s+(?:the\s+)?browser)\b", t, re.I):
        return None

    try:
        from jarvis.tools.pc_control import PCControlTool
        from jarvis import aimode, ollama_local, gemini, llm

        search_tool = PCControlTool()
        search_res = search_tool.run(action="web_search", target=query)
        results = search_res.get("results") or []
        if not results:
            return None

        snippets = "\n".join(
            "- %s: %s" % (r.get("title", ""), r.get("snippet", ""))
            for r in results[:4] if r.get("snippet")
        )
        if not snippets:
            return None

        prompt = (
            "Live web search results for %r:\n%s\n\n"
            "User request: %s\n"
            "Answer the question directly, accurately, and concisely in 1-2 spoken sentences using the live search facts above. "
            "State names, dates, or specific details clearly. Keep the JARVIS butler voice."
            % (query, snippets, text)
        )

        mode = aimode.mode()
        answer = None
        engine = "search:cloud"

        if mode == "local":
            answer = ollama_local.chat(prompt, max_tokens=100, temperature=0.1)
            engine = "search:local:" + ollama_local.preferred_model()
        else:
            try:
                answer = gemini.chat_gemini(prompt, max_tokens=120)
                if answer:
                    engine = "search:gemini"
            except Exception:
                pass
            if not answer:
                answer = llm.chat_groq(prompt, max_tokens=120)
                if answer:
                    engine = "search:groq"

        if not answer:
            return None

        return Reply(
            speech=answer.strip(),
            actions=[{"tool": "pc_control", "args": {"action": "web_search", "target": query}}],
            mood="neutral",
            tokens_used=0,
            engine=engine,
        )
    except Exception as exc:
        logger.debug("live browse failed: %s", exc)
        return None


def respond(text: str, context: Optional[List[Dict[str, Any]]] = None,
            image: Optional[bytes] = None) -> Reply:
    """Main brain entry point. Defaults to OAuth daily refreshing models with offline fallbacks."""
    # Local / Cloud switching answers itself: it is a setting, not a question.
    mode_reply = _ai_mode_intent(text)
    if mode_reply is not None:
        return mode_reply

    # Exact HUD interface commands and high-risk wipe commands stay deterministic and instant.
    t_clean = text.lower().strip()
    if re.fullmatch(r"(help|commands|show help|command index|what can you do|close help|hide help|dismiss help)[\s.!?]*", t_clean) or \
       re.search(r"\b(delete\s+all|format\b|wipe\b|destroy\b|erase\b|drop database|rm -rf)\b", t_clean):
        return _stub_respond(text, context)

    # Host control is parsed first: it needs no model, so it works even when the
    # AI brain is switched off.
    pc_actions = _detect_pc_actions(text)

    # Master switch. With the brain off, NO model is contacted: not Gemini, not
    # Groq, not the OpenCode CLI, not Ollama, not a local GGUF. The reply below is
    # a fixed string built here, so a test session cannot spend a single credit.
    try:
        from jarvis import settings as _settings

        if not _settings.flag("brain_enabled", True):
            return Reply(
                speech="The brain is switched off, sir. No AI model will answer until you switch it back on.",
                actions=pc_actions,
                mood="neutral",
                tokens_used=0,
                engine="brain-off",
            )
    except Exception:
        pass

    provider = os.environ.get("JARVIS_BRAIN_PROVIDER", "oauth").lower().strip()

    # Host control answers itself: the action runs locally, so there is no reason
    # to spend a model request on it. The daemon replaces the speech with the
    # real outcome once the action has run.
    if pc_actions:
        try:
            from jarvis import pc_intents

            spoken = pc_intents.spoken_intent(pc_actions)
        except Exception:
            spoken = "On it, sir."
        return Reply(
            speech=spoken,
            actions=pc_actions,
            mood="neutral",
            tokens_used=0,
            engine="pc-control",
        )

    # Long tail of desktop requests: "open chrome and search for flights", "put
    # the report in my documents folder". ``pc_intents`` only knows fixed
    # phrasings, so the selected model turns ordinary speech into a small,
    # whitelisted plan of pc_control actions. Destructive steps still go through
    # the normal approval gate in the daemon.
    if image is None:
        live_browse = _live_browse_intent(text)
        if live_browse is not None:
            return live_browse
        planned = _planner_respond(text)
        if planned is not None:
            return planned

    if context is None:
        context = _global_memory.get_history()

    # Local / Cloud selection. The mode is explicit and persisted; neither side
    # ever answers for the other, and a local failure is reported as a failure.
    try:
        from jarvis import aimode

        mode = aimode.mode()
    except Exception:
        mode = "cloud"

    if mode == "local":
        reply = _ollama_respond(text, context, image=image)
        if reply is None:
            try:
                from jarvis import ollama_local

                st = ollama_local.status(refresh=True)
                if not st["available"]:
                    reason = st["error"] or "Ollama is not running."
                elif image and not st.get("vision_present"):
                    reason = "the local vision model %s is not pulled." % st.get("vision_model")
                elif not st["model_present"]:
                    reason = "model %s is not pulled." % st["model"]
                else:
                    reason = ollama_local.last_error() or "the local model returned nothing."
            except Exception as exc:
                reason = str(exc)
            reply = _local_unavailable_respond(reason, pc_actions)
    elif image is not None:
        # Cloud eyes: the visual question and the frame go to Gemini in one call,
        # then a plain text answer comes back. No local model is involved.
        from jarvis import vision

        seen = vision.describe_image(image, prompt=text)
        if seen.get("ok"):
            reply = Reply(
                speech=str(seen.get("description") or "").strip(),
                actions=_detect_doubt_visual_action(text),
                mood="neutral",
                tokens_used=0,
                engine=str(seen.get("engine") or "vision"),
            )
        else:
            reply = Reply(
                speech="My eyes could not read the camera frame, sir: %s" % (seen.get("error") or "unknown error"),
                actions=[],
                mood="concerned",
                tokens_used=0,
                engine="vision-unavailable",
            )
    elif provider in ("local", "uncensored", "local_uncensored"):
        reply = _local_uncensored_respond(text, context)
        if reply is None:
            reply = _stub_respond(text, context)
    elif provider in ("oauth", "antigravity"):
        reply = _oauth_respond(text, context)
    else:
        # Default smart stub
        reply = _stub_respond(text, context)

    # Save to short term memory
    _global_memory.add_turn("user", text)
    _global_memory.add_turn("assistant", reply.speech)

    if not reply.engine:
        reply.engine = "offline-stub"

    # Host control actions ride along with the answer. The dedicated
    # ``pc_control`` tool supersedes the legacy ``pc_automation`` actions, so the
    # legacy ones are dropped to avoid running the same action twice. A real
    # WhatsApp call likewise replaces the HUD demo call action.
    if pc_actions:
        dropped = {"pc_automation"}
        if any(a.get("tool") == "whatsapp" for a in pc_actions):
            dropped.update({"call", "globalfone_call"})
        kept = [a for a in (reply.actions or []) if a.get("tool") not in dropped]
        reply.actions = kept + pc_actions

    return reply
