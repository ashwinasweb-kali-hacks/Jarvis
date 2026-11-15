"""JARVIS Daemon — Headless background service and IPC communication bridge.

Accepts commands over HTTP / JSON socket from the shell UI or test runners.
Dispatches queries to jarvis.brain and provides studio-quality neural TTS and STT.
Serves the master workshop UI over http://127.0.0.1:8765/ with secure audio/video origin.
"""
from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from jarvis.brain import Reply, respond
from jarvis.config import JarvisConfig
from jarvis import tts as voice_out
from jarvis import voice_models

logger = logging.getLogger("jarvis.daemon")
_STARTED_AT = time.time()
_SHELL_DIR = Path(__file__).resolve().parent.parent / "shell"

# Agent -> Edge voice, kept for the shell UI's /api/tts?agent= calls.
VOICE_MAP = dict(voice_models.get_tts("edge-tts")["voices"])


async def _synthesize_edge_tts(text: str, voice: str) -> bytes:
    """Backwards-compatible wrapper around the shared TTS engine."""
    outcome = voice_out.synthesize(text, voice=voice, model="edge-tts", fallback=False)
    if not outcome.get("ok"):
        raise RuntimeError(outcome.get("error", "edge-tts failed"))
    return outcome["audio"]


def _find_adb() -> Optional[str]:
    """Locate the Android Debug Bridge binary (Quest USB link)."""
    candidates = []
    local = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("PROGRAMFILES", "")
    if local:
        candidates.append(Path(local) / "Android" / "Sdk" / "platform-tools" / "adb.exe")
    candidates.append(Path("C:/platform-tools/adb.exe"))
    if local:
        candidates.append(Path(local) / "Programs" / "SideQuest" / "adb.exe")
    if program_files:
        candidates.append(Path(program_files) / "SideQuest" / "adb.exe")

    for candidate in candidates:
        try:
            if candidate.exists():
                return str(candidate)
        except OSError:
            continue

    # Fall back to whatever is on PATH.
    import shutil

    found = shutil.which("adb")
    return found


def _quest_link_info() -> Dict[str, Any]:
    """Report how the Meta Quest can reach this daemon (adb reverse tunnel)."""
    info: Dict[str, Any] = {"installed": False, "path": None, "devices": [], "reverse": False}
    adb = _find_adb()
    if not adb:
        info["hint"] = "Install Android Platform Tools (adb) to link the headset over USB."
        return info

    info["installed"] = True
    info["path"] = adb

    import subprocess

    def _run(args, timeout=6):
        try:
            proc = subprocess.run(
                [adb] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return proc.stdout or ""
        except Exception as exc:  # pragma: no cover - depends on local tooling
            info["error"] = str(exc)
            return ""

    devices = []
    for line in _run(["devices"]).splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append({"serial": parts[0], "state": parts[1]})
    info["devices"] = devices

    reverse = _run(["reverse", "--list"])
    info["reverse"] = "tcp:8765" in reverse
    if not info["reverse"]:
        info["hint"] = "Run connect-quest.bat to open the adb reverse tunnel to port 8765."
    return info


def _vision_info() -> Dict[str, Any]:
    """Describe the camera the assistant can see through."""
    try:
        from jarvis import capture

        url = capture.configured_url()
        return {
            "source": url or None,
            "configured": bool(url),
            "note": "Set JARVIS_VISION_URL to a JPEG/MJPEG camera URL for in-AR sight.",
        }
    except Exception as exc:
        return {"source": None, "configured": False, "error": str(exc)}


def _pc_info() -> Dict[str, Any]:
    """Describe the host control capability: on/off, scope and available actions."""
    try:
        from jarvis.tools.pc_control import control_enabled, full_access

        enabled = control_enabled()
        info: Dict[str, Any] = {
            "enabled": enabled,
            "full_access": full_access(),
            "actions": [],
        }
        try:
            from jarvis.tools.base import get_default_registry

            tool = get_default_registry().get("pc_control")
            if tool is not None:
                info["actions"] = list(tool.schema.get("properties", {}).get("action", {}).get("enum", []))
        except Exception:
            pass
        info["note"] = (
            "Voice commands are parsed locally and executed on the host: open and close "
            "apps, drive the mouse and keyboard, read the screen with UI Automation and "
            "OCR, read/write/delete files, run PowerShell, install via winget, browse, "
            "lock, shut down, restart, screenshot, volume, processes and workflows."
        )
        return info
    except Exception as exc:
        return {"enabled": False, "error": str(exc)}


def _voice_selftest() -> Dict[str, Any]:
    """Report the selected TTS/STT engines and the audio devices the daemon sees."""
    info: Dict[str, Any] = {"ok": True, "tts": {}, "stt": {}, "audio": {}}

    try:
        catalog = voice_models.list_voice_models(live=True)
    except Exception as exc:
        catalog = {}
        info["catalog_error"] = str(exc)

    try:
        selected_tts = voice_models.tts_model()
        tts_entry = next(
            (m for m in catalog.get("tts", {}).get("models", []) if m.get("id") == selected_tts),
            {},
        )
        tts_version = None
        package = tts_entry.get("package")
        if package:
            try:
                from importlib.metadata import version as package_version

                tts_version = package_version(package)
            except Exception:
                tts_version = None

        available = bool(tts_entry.get("installed", False))
        info["tts"] = {
            "engine": selected_tts,
            "label": tts_entry.get("label", selected_tts),
            "available": available,
            "version": tts_version,
            "voices": tts_entry.get("voices", {}),
            "offline": bool(tts_entry.get("offline", False)),
            "error": None if available else "engine package not installed",
        }
    except Exception as exc:
        info["tts"] = {
            "engine": "unknown",
            "available": False,
            "error": str(exc),
            "voices": {},
        }

    try:
        config = JarvisConfig.from_env()
        rows = (catalog.get("stt") or {}).get("models", [])
        selected_stt = voice_models.stt_model()
        chosen = next((m for m in rows if m.get("id") == selected_stt), None)
        if chosen is None:
            chosen = {
                "id": selected_stt,
                "label": selected_stt,
                "engine": "faster_whisper",
                "model": voice_models.whisper_size(),
                "installed": True,
                "offline": True,
            }

        picked = [chosen]
        fallback_id = chosen.get("fallback")
        if fallback_id:
            fallback = next((m for m in rows if m.get("id") == fallback_id), None)
            if fallback:
                picked.append(fallback)

        engines = []
        for model in picked:
            available = bool(model.get("installed", False))
            provider = model.get("key_provider")
            error = None
            if not available:
                if provider and not model.get("package"):
                    error = f"{provider.upper()}_API_KEY not set"
                else:
                    error = "engine package not installed"
            engines.append({
                "name": model.get("label", model.get("id")),
                "id": model.get("id"),
                "engine": model.get("engine"),
                "available": available,
                "selected": model.get("id") == selected_stt,
                "offline": bool(model.get("offline")),
                "model": model.get("model"),
                "error": error,
            })

        info["stt"] = {
            "engines": engines,
            "model": engines[0]["model"] if engines else voice_models.whisper_size(),
            "selected": selected_stt,
            "fallback": fallback_id,
            "language": config.language,
            "device": config.device,
        }
    except Exception as exc:
        info["stt"] = {"engines": [], "error": str(exc)}

    try:
        import sounddevice as sd

        devices = list(sd.query_devices())
        default_in, default_out = list(sd.default.device)[:2]

        inputs = []
        outputs = []
        for index, dev in enumerate(devices):
            entry = {"index": index, "name": dev.get("name", "Unknown")}
            if dev.get("max_input_channels", 0) > 0:
                inputs.append(entry)
            if dev.get("max_output_channels", 0) > 0:
                outputs.append(entry)

        def _name(entries, index):
            for entry in entries:
                if entry["index"] == index:
                    return entry["name"]
            return None

        info["audio"] = {
            "default_input": default_in,
            "default_output": default_out,
            "input_name": _name(inputs, default_in),
            "output_name": _name(outputs, default_out),
            "input_devices": inputs,
            "output_devices": outputs,
        }
    except Exception as exc:
        info["audio"] = {"error": str(exc)}

    try:
        info["quest"] = _quest_link_info()
    except Exception as exc:
        info["quest"] = {"error": str(exc)}

    brain_info: Dict[str, Any] = {}
    try:
        from jarvis import brain as brain_module

        brain_info = {
            "provider": JarvisConfig.from_env().brain_provider,
            "opencode_cli": brain_module.OPENCODE_CLI_PATH,
            "model": brain_module.ACTIVE_MODEL,
        }
    except Exception as exc:
        brain_info = {"error": str(exc)}
    try:
        from jarvis import gemini

        brain_info["gemini"] = gemini.chat_available()
        brain_info["gemini_model"] = os.environ.get("JARVIS_GEMINI_MODEL", gemini.DEFAULT_GEMINI_MODEL)
        brain_info["gemini_cooldowns"] = gemini.cooldowns()
        brain_info["gemini_error"] = gemini.last_error()
    except Exception:
        brain_info["gemini"] = False
    try:
        from jarvis import llm

        brain_info["groq_chat"] = llm.chat_available()
    except Exception:
        brain_info["groq_chat"] = False
    info["brain"] = brain_info

    return info


class JarvisDaemonHandler(BaseHTTPRequestHandler):
    """HTTP/JSON RPC and Media Streaming handler for JARVIS."""

    def _send_json(self, status: int, data: Dict[str, Any]) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path in ("/status", "/api/status"):
            config = JarvisConfig.from_env()
            self._send_json(200, {
                "status": "online",
                "service": "jarvis-daemon",
                "provider": config.brain_provider,
                "address": config.address,
                "stt_model": config.stt_model,
                "tts_model": config.tts_model,
            })
            return

        if path in ("/api/bubble", "/bubble"):
            try:
                from jarvis import bubblectl

                self._send_json(200, bubblectl.status())
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": str(exc)})
            return

        if path in ("/api/health", "/health"):
            from jarvis import keyvault
            from jarvis.tools.base import get_default_registry

            config = JarvisConfig.from_env()
            registry = get_default_registry()
            tls_on = os.environ.get("JARVIS_TLS", "").strip().lower() in ("1", "true", "yes", "on")
            configured = [k["provider"] for k in keyvault.list_keys() if k["configured"]]

            brain_info: Dict[str, Any] = {"provider": config.brain_provider}
            try:
                from jarvis import brain as brain_module

                brain_info["opencode_cli"] = brain_module.OPENCODE_CLI_PATH
                brain_info["model"] = brain_module.ACTIVE_MODEL
            except Exception as exc:
                brain_info["error"] = str(exc)
            try:
                from jarvis import gemini

                brain_info["gemini"] = gemini.chat_available()
                brain_info["gemini_model"] = os.environ.get("JARVIS_GEMINI_MODEL", gemini.DEFAULT_GEMINI_MODEL)
                brain_info["gemini_cooldowns"] = gemini.cooldowns()
                brain_info["gemini_error"] = gemini.last_error()
            except Exception:
                brain_info["gemini"] = False
            try:
                from jarvis import settings as settings_module

                brain_info["enabled"] = settings_module.flag("brain_enabled", True)
                brain_info["gemini_enabled"] = settings_module.flag("gemini_enabled", True)
            except Exception:
                brain_info["enabled"] = True
                brain_info["gemini_enabled"] = True
            try:
                from jarvis import llm

                brain_info["groq_chat"] = llm.chat_available()
            except Exception:
                brain_info["groq_chat"] = False

            try:
                from jarvis import aimode

                ai_info = aimode.status()
            except Exception as exc:
                ai_info = {"mode": "cloud", "error": str(exc)}

            self._send_json(200, {
                "status": "online",
                "uptime_seconds": int(time.time() - _STARTED_AT),
                "scheme": "https" if tls_on else "http",
                "brain_provider": config.brain_provider,
                "brain": brain_info,
                "ai": ai_info,
                "address": config.address,
                "tools": len(registry.list_tools()),
                "tool_names": [t["name"] for t in registry.list_tools()],
                "keys_configured": configured,
                "vr": {
                    "webxr_needs_https": True,
                    "https_enabled": tls_on,
                    "note": "Headset browsers only expose WebXR on a secure context.",
                },
                "quest": _quest_link_info(),
                "vision": _vision_info(),
                "pc": _pc_info(),
            })
            return

        if path in ("/api/pc/whatsapp", "/pc/whatsapp", "/api/whatsapp", "/whatsapp"):
            try:
                from jarvis import wa

                self._send_json(200, {
                    "ok": True,
                    "allowed_numbers": wa.allowed_numbers(),
                    "app_running": wa.app_running(),
                    "protocol": wa.protocol_available(),
                    "contacts": wa.load_contacts(),
                })
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})
            return

        if path in ("/api/pc", "/pc"):
            info = _pc_info()
            self._send_json(200, {"ok": True, **info})
            return

        if path in ("/api/ai", "/ai", "/api/mode"):
            try:
                from jarvis import aimode

                self._send_json(200, {"ok": True, **aimode.status()})
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": str(exc)})
            return

        if path in ("/api/screen", "/screen"):
            try:
                from jarvis import screen

                data = screen.snapshot(with_ocr=True)
                self._send_json(200, {
                    "ok": True,
                    "window": data.get("window"),
                    "elements": data.get("elements", [])[:80],
                    "element_count": data.get("element_count"),
                    "text": (data.get("text") or "")[:4000],
                    "spoken": screen.describe(data),
                    "elapsed_ms": data.get("elapsed_ms"),
                    "errors": data.get("errors"),
                })
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": str(exc)})
            return

        if path in ("/api/browser", "/browser"):
            try:
                from jarvis import browser

                self._send_json(200, {"ok": True, **browser.status()})
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": str(exc)})
            return

        if path in ("/api/workflow", "/workflow"):
            try:
                from jarvis import approvals, workflow

                self._send_json(200, {"ok": True, "workflow": workflow.pending(), "approval": approvals.pending()})
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": str(exc)})
            return

        if path in ("/api/email", "/email"):
            try:
                from jarvis import mailbox

                self._send_json(200, {"ok": True, "config": mailbox.configured()})
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": str(exc)})
            return

        if path in ("/api/settings", "/settings"):
            from jarvis.settings import all_settings
            payload = all_settings()
            payload.setdefault("brain_enabled", True)
            payload.setdefault("gemini_enabled", True)
            payload.setdefault("ai_mode", "cloud")
            self._send_json(200, {"ok": True, "settings": payload})
            return

        if path in ("/api/auth/claude", "/auth/claude"):
            try:
                from jarvis.claude_oauth import start_oauth_flow
                auth_url = start_oauth_flow(open_browser=True)
                self._send_json(200, {
                    "ok": True,
                    "auth_url": auth_url,
                    "message": "Opening Claude authentication in your browser."
                })
                return
            except Exception as e:
                logger.exception("Claude OAuth flow initialization error: %s", e)
                self._send_json(500, {"error": str(e)})
                return

        if path in ("/api/tts", "/tts"):
            query = urllib.parse.parse_qs(parsed_url.query)
            text = query.get("text", [""])[0].strip()
            agent = query.get("agent", ["jarvis"])[0].lower().strip()
            model = query.get("model", [None])[0] or voice_models.tts_model()

            if not text:
                self._send_json(400, {"error": "Missing 'text' parameter"})
                return

            outcome = voice_out.synthesize(text, agent=agent, model=model)
            if not outcome.get("ok"):
                logger.error("Error synthesizing speech: %s", outcome.get("error"))
                self._send_json(500, {"error": outcome.get("error", "TTS failed")})
                return

            audio_bytes = outcome["audio"]
            self.send_response(200)
            self.send_header("Content-Type", outcome.get("mime", "audio/mpeg"))
            self.send_header("Content-Length", str(len(audio_bytes)))
            self.send_header("X-Jarvis-TTS-Model", str(outcome.get("model", model)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(audio_bytes)
            return

        if path in ("/api/voice/models", "/voice/models"):
            self._send_json(200, {"ok": True, **voice_models.list_voice_models(live=True)})
            return

        if path in ("/api/voice/selftest", "/voice/selftest"):
            self._send_json(200, _voice_selftest())
            return

        # Favicon request (avoid noisy browser 404 logs)
        if path in ("/favicon.ico", "favicon.ico"):
            self.send_response(204)
            self.end_headers()
            return

        # Serve Workshop HUD static files
        req_path = path.lstrip("/")
        if not req_path or req_path in ("index.html", "shell", "shell/index.html"):
            target_file = _SHELL_DIR / "index.html"
        else:
            clean_name = req_path.replace("shell/", "")
            target_file = _SHELL_DIR / clean_name

        if target_file.exists() and target_file.is_file():
            content = target_file.read_bytes()
            mime = "text/html"
            if target_file.suffix == ".js":
                mime = "application/javascript"
            elif target_file.suffix == ".css":
                mime = "text/css"
            elif target_file.suffix == ".mp3":
                mime = "audio/mpeg"
            elif target_file.suffix == ".mp4":
                mime = "video/mp4"
            elif target_file.suffix in (".png", ".jpg", ".jpeg"):
                mime = "image/png"

            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            # The HUD is edited in place; never let the browser pin an old copy.
            self.send_header("Cache-Control", "no-store" if mime == "text/html" else "public, max-age=300")
            self.end_headers()
            self.wfile.write(content)
            return

        self._send_json(404, {"error": f"Endpoint not found: {path}"})

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.rstrip("/")
        logger.debug("do_POST path='%s' (raw='%s')", path, self.path)

        if path in ("/api/bubble", "/bubble"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}
                action = str(req.get("action") or req.get("op") or "status").lower()
                from jarvis import bubblectl

                if action in ("start", "open", "show", "on"):
                    result = bubblectl.start()
                elif action in ("stop", "close", "hide", "off", "quit"):
                    result = bubblectl.stop()
                elif action == "toggle":
                    result = bubblectl.toggle()
                else:
                    result = bubblectl.status()
                if action in ("start", "open", "show", "on") and result.get("started"):
                    try:
                        from jarvis import settings as _settings

                        _settings.set("bubble_enabled", True)
                    except Exception:
                        pass
                self._send_json(200, result)
            except Exception as exc:
                logger.exception("Bubble control failed: %s", exc)
                self._send_json(500, {"ok": False, "error": str(exc)})
            return

        if path in ("/api/command", "/command", "/chat"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}
                text = req.get("text", "").strip()

                if not text:
                    self._send_json(400, {"error": "Missing 'text' field"})
                    return

                # Live video conversation: the page attaches one camera frame to
                # the utterance, so the assistant answers about what it sees now.
                image_bytes = None
                raw_image = str(req.get("image") or "")
                if raw_image.startswith("data:image/"):
                    import base64

                    header, _, encoded = raw_image.partition(",")
                    try:
                        image_bytes = base64.b64decode(encoded)
                    except Exception:
                        image_bytes = None

                started = time.time()

                # A parked irreversible action answers "confirm" / "cancel"
                # before the model chain is even consulted, so a yes cannot be
                # mistaken for a new command.
                from jarvis import approvals

                parked = approvals.pending()
                if parked.get("pending") and approvals.is_affirmative(text):
                    outcome = approvals.confirm()
                    elapsed = int((time.time() - started) * 1000)
                    self._send_json(200, {
                        "ok": True,
                        "reply": {"speech": outcome.get("speech") or "Done, sir.",
                                  "actions": [], "needs_confirmation": False,
                                  "mood": "neutral", "tokens_used": 0, "engine": "approval"},
                        "engine": "approval",
                        "elapsed_ms": elapsed,
                        "result": outcome.get("result"),
                    })
                    return
                if parked.get("pending") and approvals.is_negative(text):
                    outcome = approvals.cancel()
                    self._send_json(200, {
                        "ok": True,
                        "reply": {"speech": outcome.get("speech") or "Cancelled, sir.",
                                  "actions": [], "needs_confirmation": False,
                                  "mood": "neutral", "tokens_used": 0, "engine": "approval"},
                        "engine": "approval",
                        "elapsed_ms": int((time.time() - started) * 1000),
                    })
                    return

                reply: Reply = respond(text, image=image_bytes)
                brain_ms = int((time.time() - started) * 1000)

                # Execute automation tool actions directly on host PC
                from jarvis.tools.base import get_default_registry
                reg = get_default_registry()
                executed_actions = []
                pc_results = []
                confirm_speech = ""
                for act in reply.actions:
                    t_name = act.get("tool")
                    t_args = dict(act.get("args") or {})
                    if t_name and reg.get(t_name):
                        if approvals.needs_confirmation(t_name, t_args) and req.get("confirm") is not True:
                            parked_action = approvals.request(t_name, t_args)
                            confirm_speech = parked_action.get("message") or confirm_speech
                            continue
                        res = reg.execute(t_name, args=t_args)
                        executed_actions.append(res)
                        if t_name in ("pc_control", "whatsapp"):
                            pc_results.append(res.get("result") or {"ok": res.get("ok"), "error": res.get("error")})

                resp_data = reply.to_dict()
                if executed_actions:
                    resp_data["executed_actions"] = executed_actions

                # Host actions speak for themselves: report what actually happened
                # instead of the model's guess about it, unless the model was answering
                # a search/browse query with live synthesized speech.
                if pc_results and not str(reply.engine or "").startswith("search:"):
                    try:
                        from jarvis import pc_intents

                        spoken = pc_intents.summarise(pc_results)
                        if spoken:
                            resp_data["speech"] = spoken
                    except Exception:
                        pass

                if confirm_speech:
                    resp_data["speech"] = confirm_speech
                    resp_data["needs_confirmation"] = True

                self._send_json(200, {
                    "ok": True,
                    "reply": resp_data,
                    "engine": reply.engine,
                    "elapsed_ms": brain_ms,
                })
            except Exception as e:
                logger.exception("Error processing command: %s", e)
                self._send_json(500, {"error": str(e)})

        elif path in ("/api/vision", "/vision"):
            """Describe a camera frame with Gemini (the assistant's eyes)."""
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}
                data_url = str(req.get("image", ""))
                prompt = str(req.get("prompt", "")).strip() or None
                source = str(req.get("source", "")).strip().lower()
                camera_url = str(req.get("url", "")).strip() or None

                mime = "image/jpeg"
                if source in ("server", "camera") or (not data_url and camera_url):
                    # Server-side capture: works even while an XR session owns
                    # the headset camera.
                    from jarvis import capture

                    try:
                        image_bytes = capture.fetch_frame(camera_url)
                    except Exception as exc:
                        self._send_json(502, {
                            "ok": False,
                            "description": "",
                            "engine": None,
                            "error": str(exc),
                            "errors": [str(exc)],
                            "elapsed_ms": 0,
                            "bytes": 0,
                        })
                        return
                elif data_url.startswith("data:image/"):
                    import base64

                    header, _, encoded = data_url.partition(",")
                    mime = header[5:].split(";")[0] or "image/jpeg"
                    try:
                        image_bytes = base64.b64decode(encoded)
                    except Exception as exc:
                        self._send_json(400, {"ok": False, "error": "bad base64: {0}".format(exc)})
                        return
                else:
                    self._send_json(400, {"ok": False, "error": "expected a data:image/... payload or source=server"})
                    return

                from jarvis import vision

                result = vision.describe_image(image_bytes, prompt=prompt, mime=mime)
                self._send_json(200 if result.get("ok") else 502, {
                    "ok": result.get("ok"),
                    "description": result.get("description"),
                    "engine": result.get("engine"),
                    "mode": result.get("mode"),
                    "error": result.get("error"),
                    "errors": result.get("errors", []),
                    "elapsed_ms": result.get("elapsed_ms"),
                    "bytes": len(image_bytes),
                })
            except Exception as e:
                logger.exception("Error processing vision request: %s", e)
                self._send_json(500, {"ok": False, "error": str(e)})

        elif path in ("/api/stt", "/stt", "/api/voice/test-stt"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                audio_bytes = self.rfile.read(length)
                if not audio_bytes:
                    self._send_json(400, {"ok": False, "text": "", "error": "Empty audio payload"})
                    return

                from jarvis import stt as voice_in

                detail = voice_in.transcribe_wav_bytes_ex(audio_bytes)

                payload = {
                    "ok": detail["ok"],
                    "text": detail["text"],
                    "engine": detail["engine"],
                    "model": detail["model"],
                    "fallback": detail["fallback"],
                    "elapsed_ms": detail["elapsed_ms"],
                    "error": detail["error"],
                    "reason": detail.get("reason"),
                    "message": detail.get("message"),
                    "level": detail.get("level"),
                }
                if path == "/api/voice/test-stt":
                    payload["bytes"] = len(audio_bytes)
                    payload["attempt_errors"] = detail.get("errors", [])
                if not detail["ok"]:
                    logger.warning("Speech recognition failed: %s", detail["error"])
                self._send_json(200, payload)
            except Exception as e:
                logger.exception("Error processing STT: %s", e)
                self._send_json(500, {"ok": False, "text": "", "error": str(e)})

        elif path in ("/api/call", "/call"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}
                target = req.get("target", "Friend")
                from jarvis.tools.call import CallTool
                res = CallTool().run(target=target)
                self._send_json(200, {"ok": True, "call": res})
            except Exception as e:
                self._send_json(500, {"error": str(e)})

        elif path in ("/api/settings", "/settings"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}
                key = req.get("key")
                value = req.get("value")
                if key is None:
                    self._send_json(400, {"error": "Missing 'key' field"})
                    return
                from jarvis.settings import set as set_setting, get as get_setting

                set_setting(str(key), value)
                self._send_json(200, {"ok": True, "key": key, "value": get_setting(str(key))})
            except Exception as e:
                logger.exception("Error saving setting: %s", e)
                self._send_json(500, {"error": str(e)})

        elif path in ("/api/webrtc/signal", "/webrtc/signal"):
            try:
                from jarvis.webrtc import signal_room
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}
                room = str(req.get("room", "default"))
                peer = str(req.get("peer", "unknown"))
                sdp = req.get("sdp")
                candidate = req.get("candidate")
                out = signal_room(room, peer, sdp=sdp, candidate=candidate)
                self._send_json(200, {"ok": True, "signal": out})
            except Exception as e:
                logger.exception("WebRTC signaling error: %s", e)
                self._send_json(500, {"error": str(e)})

        elif path in ("/api/mic/record_host", "/mic/record_host"):
            try:
                import io
                import wave
                import numpy as np
                import sounddevice as sd
                from jarvis import stt as voice_in
                fs = 16000
                rec = sd.rec(int(3.0 * fs), samplerate=fs, channels=1, dtype='int16')
                sd.wait()
                buf = io.BytesIO()
                with wave.open(buf, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(fs)
                    wf.writeframes(rec.tobytes())
                detail = voice_in.transcribe_wav_bytes_ex(buf.getvalue())
                self._send_json(200, {
                    "ok": detail["ok"],
                    "text": detail["text"],
                    "engine": detail["engine"],
                    "model": detail["model"],
                    "fallback": detail["fallback"],
                    "elapsed_ms": detail["elapsed_ms"],
                    "error": detail["error"],
                    "reason": detail.get("reason"),
                    "message": detail.get("message"),
                    "level": detail.get("level"),
                })
            except Exception as e:
                self._send_json(200, {"ok": False, "text": "", "error": str(e)})

        elif path in ("/api/pc", "/pc"):
            """Direct host control: {"action": "...", ...args} or {"text": "open notepad"}."""
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}

                from jarvis.tools.base import get_default_registry
                from jarvis.tools.pc_control import control_enabled, full_access

                if not control_enabled():
                    self._send_json(403, {
                        "ok": False,
                        "error": "PC control is switched off (pc_control_enabled).",
                    })
                    return

                reg = get_default_registry()

                # Plain language: parse it locally, no AI model involved.
                text = str(req.get("text", "")).strip()
                if text and not req.get("action"):
                    from jarvis import pc_intents

                    planned = pc_intents.detect(text)
                    if not planned:
                        self._send_json(400, {
                            "ok": False,
                            "error": "I did not recognise a PC action in that.",
                            "text": text,
                        })
                        return
                    results = []
                    for act in planned:
                        t_args = dict(act.get("args") or {})
                        res = reg.execute("pc_control", args=t_args, confirmed=True)
                        results.append(res.get("result") or {"ok": res.get("ok"), "error": res.get("error")})
                    ok = all(bool(r.get("ok")) for r in results)
                    self._send_json(200 if ok else 500, {
                        "ok": ok,
                        "text": text,
                        "actions": [a.get("args") for a in planned],
                        "results": results,
                        "message": pc_intents.summarise(results),
                        "full_access": full_access(),
                    })
                    return

                action = str(req.get("action", "")).strip().lower()
                if not action:
                    self._send_json(400, {"error": "Missing 'action' field"})
                    return

                args = dict(req)  # keeps "action" - the tool reads it from kwargs
                res = reg.execute("pc_control", args=args, confirmed=True)
                result = res.get("result") or {}
                payload = {
                    "ok": bool(res.get("ok")) and bool(result.get("ok", True)),
                    "action": action,
                    "result": result,
                    "error": res.get("error") or result.get("error"),
                    "message": result.get("message"),
                    "full_access": full_access(),
                }
                self._send_json(200 if payload["ok"] else 500, payload)
            except Exception as e:
                logger.exception("Error running PC action: %s", e)
                self._send_json(500, {"error": str(e)})

        elif path in ("/api/ai", "/ai", "/api/mode"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}

                from jarvis import aimode, ollama_local

                if req.get("start") is True:
                    self._send_json(200, {"ok": True, "ollama": ollama_local.start_service(), **aimode.status()})
                    return
                if req.get("load") is True:
                    self._send_json(200, {"ok": True, "ollama": ollama_local.load(), **aimode.status()})
                    return
                if req.get("vision") is True:
                    # Warm the multimodal model when live vision is switched on,
                    # so the first frame is not a cold start. ``wait`` blocks
                    # until it is resident (used while the HUD shows progress).
                    self._send_json(200, {
                        "ok": True,
                        "ollama": ollama_local.ensure_warm(
                            background=not bool(req.get("wait")),
                            model=ollama_local.vision_model_name(),
                        ),
                        **aimode.status(),
                    })
                    return
                if req.get("unload") is True:
                    self._send_json(200, {"ok": True, "ollama": ollama_local.unload(), **aimode.status()})
                    return
                if req.get("mode"):
                    result = aimode.set_mode(str(req["mode"]))
                    self._send_json(200 if result.get("ok") else 400, {"ok": result.get("ok"), **result})
                    return
                self._send_json(200, {"ok": True, **aimode.status()})
            except Exception as exc:
                logger.exception("AI mode error: %s", exc)
                self._send_json(500, {"ok": False, "error": str(exc)})

        elif path in ("/api/screen", "/screen"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}

                from jarvis import screen

                action = str(req.get("action") or "describe").lower()
                if action in ("read", "text", "ocr"):
                    data = screen.snapshot(with_ocr=True)
                    self._send_json(200, {"ok": True, "text": (data.get("text") or "")[:6000],
                                          "window": data.get("window"), "elements": data.get("elements", [])[:100],
                                          "spoken": screen.describe(data), "elapsed_ms": data.get("elapsed_ms")})
                elif action == "click":
                    self._send_json(200, {"ok": True, **screen.click_element(str(req.get("target") or req.get("text") or ""))})
                elif action == "vision":
                    result = screen.describe_with_vision(req.get("prompt"))
                    self._send_json(200 if result.get("ok") else 502, result)
                elif action == "screenshot":
                    shot = screen.screenshot(window_only=bool(req.get("window_only", True)))
                    self._send_json(200, {"ok": True, **shot})
                else:
                    data = screen.snapshot(with_ocr=True)
                    self._send_json(200, {"ok": True, "spoken": screen.describe(data), "window": data.get("window"),
                                          "element_count": data.get("element_count"),
                                          "elements": data.get("elements", [])[:60]})
            except Exception as exc:
                logger.exception("Screen error: %s", exc)
                self._send_json(500, {"ok": False, "error": str(exc)})

        elif path in ("/api/browser", "/browser"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}

                from jarvis import browser

                action = str(req.get("action") or "status")
                args = {k: v for k, v in req.items() if k != "action"}
                out = browser.run(action, **args)
                out.setdefault("message", out.get("error") or ("Browser: {0}".format(action)))
                self._send_json(200 if out.get("ok") else 500, out)
            except Exception as exc:
                logger.exception("Browser error: %s", exc)
                self._send_json(500, {"ok": False, "error": str(exc)})

        elif path in ("/api/workflow", "/workflow", "/api/approve", "/approve"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}

                from jarvis import approvals, workflow

                if req.get("cancel") is True:
                    out = approvals.cancel()
                    workflow.clear_pending()
                    self._send_json(200, {"ok": True, "speech": out.get("speech"), "cancelled": out.get("cancelled")})
                    return
                if req.get("confirm") is True:
                    if approvals.pending().get("pending"):
                        out = approvals.confirm()
                    elif workflow.pending().get("pending"):
                        out = workflow.confirm()
                        out.setdefault("speech", out.get("summary") or out.get("error") or "Done, sir.")
                    else:
                        self._send_json(404, {"ok": False, "error": "nothing is waiting for confirmation"})
                        return
                    self._send_json(200 if out.get("ok") else 500, {"ok": bool(out.get("ok")),
                                                                    "speech": out.get("speech") or out.get("error"),
                                                                    **{k: v for k, v in out.items() if k not in ("speech", "steps")},
                                                                    "steps": out.get("steps")})
                    return
                steps = req.get("steps")
                if not isinstance(steps, list) or not steps:
                    self._send_json(200, {"ok": True, "workflow": workflow.pending(), "approval": approvals.pending()})
                    return
                out = workflow.run(steps, confirmed=bool(req.get("confirmed")), label=str(req.get("label") or ""))
                out.setdefault("speech", out.get("summary") or out.get("error") or "")
                self._send_json(200 if out.get("ok") else (428 if out.get("needs_confirmation") else 500), out)
            except Exception as exc:
                logger.exception("Workflow error: %s", exc)
                self._send_json(500, {"ok": False, "error": str(exc)})

        elif path in ("/api/email", "/email"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}

                from jarvis import mailbox

                if req.get("password"):
                    from jarvis import keyvault

                    stored = keyvault.set_key("email-password", str(req["password"]))
                    self._send_json(200, {"ok": bool(stored.get("ok", True)), "password_set": True,
                                          "config": mailbox.configured()})
                    return
                action = str(req.get("action") or "config").lower()
                if action == "send":
                    out = mailbox.send(str(req.get("to") or ""), str(req.get("subject") or ""), str(req.get("body") or ""))
                elif action in ("unread", "read", "inbox"):
                    out = mailbox.unread(limit=int(req.get("limit") or 5))
                elif action == "calendar":
                    out = mailbox.calendar(days=int(req.get("days") or 1))
                elif action == "compose":
                    out = mailbox.compose(str(req.get("to") or ""), str(req.get("subject") or ""), str(req.get("body") or ""))
                else:
                    out = {"ok": True, "config": mailbox.configured()}
                self._send_json(200 if out.get("ok") else 400, out)
            except Exception as exc:
                logger.exception("Email error: %s", exc)
                self._send_json(500, {"ok": False, "error": str(exc)})

        elif path in ("/api/config", "/config"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                cfg = json.loads(body) if body else {}

                if "provider" in cfg and cfg["provider"]:
                    os.environ["JARVIS_BRAIN_PROVIDER"] = cfg["provider"].strip()

                self._send_json(200, {"ok": True, "message": "Configuration updated successfully."})
            except Exception as e:
                logger.exception("Error updating config: %s", e)
                self._send_json(500, {"error": str(e)})
        else:
            self._send_json(404, {"error": "Unknown POST endpoint"})

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("%s - - [%s] %s", self.client_address[0], self.log_date_time_string(), format % args)


class JarvisDaemon:
    """Long-running JARVIS daemon thread / process."""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        config = JarvisConfig.from_env()
        self.host = host or config.daemon_host
        self.port = port or config.daemon_port
        self.server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self, blocking: bool = False) -> None:
        self.server = ThreadingHTTPServer((self.host, self.port), JarvisDaemonHandler)

        wants_tls = os.environ.get("JARVIS_TLS", "").strip().lower() in ("1", "true", "yes", "on")
        self.scheme = "http"
        if wants_tls:
            from jarvis.tls import ensure_certificate, wrap_server_socket

            pair = ensure_certificate()
            if pair:
                cert_file, key_file = pair
                try:
                    wrap_server_socket(self.server, cert_file, key_file)
                    self.scheme = "https"
                    logger.info("TLS enabled (self-signed certificate will warn once)")
                except Exception as exc:
                    logger.warning("TLS setup failed, continuing on plain http: %s", exc)
            else:
                logger.warning("TLS requested but unavailable; serving plain http")

        logger.info("JARVIS Daemon listening on %s://%s:%d", self.scheme, self.host, self.port)

        # The floating bubble is a separate process; bring it back if the user
        # left it open last time so it keeps living in the background.
        try:
            from jarvis import bubblectl, settings as _settings

            if _settings.flag("bubble_enabled", False):
                threading.Thread(target=bubblectl.ensure_started, daemon=True).start()
        except Exception as exc:
            logger.debug("bubble autostart skipped: %s", exc)

        if blocking:
            try:
                self.server.serve_forever()
            except KeyboardInterrupt:
                self.stop()
        else:
            self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        if self.server:
            logger.info("Shutting down JARVIS Daemon...")
            self.server.shutdown()
            self.server.server_close()
            self.server = None


def main() -> None:
    from jarvis.config import setup_logging
    setup_logging()
    daemon = JarvisDaemon()
    print(f"JARVIS Daemon starting on {daemon.host}:{daemon.port} (Press Ctrl+C to stop)")
    daemon.start(blocking=True)


if __name__ == "__main__":
    main()
