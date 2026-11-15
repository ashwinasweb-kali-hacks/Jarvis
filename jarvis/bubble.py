"""macOS Dynamic-Island style popup for J.A.R.V.I.S.

A frameless, always-on-top capsule at the top centre of the screen. Collapsed it
is a small status pill; click it and it opens into a working panel with the
mode chip, the last answer, a text box and a microphone that runs the whole
voice loop (record -> /api/stt -> /api/command -> /api/tts).

It runs as its own process (``pythonw -m jarvis.bubble``) so it keeps working
with the HUD tab closed and while other applications are in front. All the
thinking still happens in the daemon; the bubble is only a client, which is why
LOCAL mode answers without touching the network.

Everything here is stdlib + the packages the project already ships: tkinter,
numpy, sounddevice, soundfile.
"""
from __future__ import annotations

import io
import json
import os
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

import tkinter as tk
from tkinter import font as tkfont

from . import settings as jsettings

DAEMON = os.environ.get("JARVIS_DAEMON_URL", "http://127.0.0.1:8765").rstrip("/")

# The canvas background is punched out with -transparentcolor, which is what
# gives the capsule real rounded corners on Windows.
TRANSPARENT = "#010203"
PANEL = "#0b0e14"
EDGE = "#1d2734"
ACCENT = "#4fd8ff"
TEXT = "#e9f5ff"
DIM = "#7f8ea3"
GOOD = "#3ddc97"
WARN = "#ffb454"
BAD = "#ff6b6b"

W_COLLAPSED = 330
H_COLLAPSED = 46
W_OPEN = 468
H_OPEN = 276
MARGIN_TOP = 10
LOCK_PORT = 8799

LOG_PATH = Path(os.environ.get("JARVIS_LOG_DIR", str(Path.home() / ".jarvis"))) / "bubble.log"


def log(message: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%H:%M:%S")
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write("[%s] %s\n" % (stamp, message))
    except Exception:
        pass


# --------------------------------------------------------------------------- http
def _json(path: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 60.0,
          method: Optional[str] = None) -> Dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        DAEMON + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method or ("POST" if data is not None else "GET"),
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def _post_audio(path: str, payload: bytes, timeout: float = 120.0) -> Dict[str, Any]:
    req = urllib.request.Request(DAEMON + path, data=payload,
                                 headers={"Content-Type": "audio/wav"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def daemon_up() -> bool:
    try:
        _json("/api/health", timeout=2.5)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- ui
def rounded_points(x1: float, y1: float, x2: float, y2: float, r: float):
    """Corner points for a smooth polygon that reads as a rounded rectangle."""
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


class Bubble:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.width = W_COLLAPSED
        self.height = H_COLLAPSED
        self.x: Optional[int] = None
        self.expanded = False
        self.busy = False
        self.listening = False
        self.mode = "cloud"
        self.engine = ""
        self.reply = "Standing by, sir."
        self.status = "tap to open"
        self.accent = ACCENT
        self._drag: Optional[Dict[str, Any]] = None
        self._anim: Optional[str] = None
        self._voice_thread: Optional[threading.Thread] = None
        self._lock: Optional[socket.socket] = None
        self._pulse = 0.0

        self._setup_window()
        self._build()
        self._draw()
        self.refresh_mode()
        self._pulse_loop()

    # -- window ------------------------------------------------------------
    def _setup_window(self) -> None:
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                import ctypes

                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT)
        try:
            self.root.attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            pass
        self.root.title("JARVIS")
        self.screen_w = self.root.winfo_screenwidth()
        self._place_window()

    def _place_window(self) -> None:
        x = self.x if self.x is not None else max(0, (self.screen_w - self.width) // 2)
        self.root.geometry("%dx%d+%d+%d" % (self.width, self.height, x, MARGIN_TOP))

    def _build(self) -> None:
        self.canvas = tk.Canvas(self.root, bg=TRANSPARENT, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Button-3>", self._menu)

        family = "Segoe UI"
        self.font_title = tkfont.Font(family=family, size=10, weight="bold")
        self.font_small = tkfont.Font(family=family, size=8)
        self.font_body = tkfont.Font(family=family, size=9)
        self.font_glyph = tkfont.Font(family=family, size=11, weight="bold")

        self.reply_label = tk.Label(
            self.root, text=self.reply, bg=PANEL, fg=TEXT, font=(family, 9),
            justify="left", anchor="nw", wraplength=W_OPEN - 54, bd=0, padx=0, pady=0,
        )
        self.entry = tk.Entry(
            self.root, bg="#121924", fg=TEXT, insertbackground=ACCENT, bd=0,
            relief="flat", highlightthickness=0, font=(family, 9),
        )
        self.entry.bind("<Return>", self._submit)
        self.entry.bind("<Escape>", lambda _e: self.collapse())

        self.menu = tk.Menu(self.root, tearoff=0, bg="#0e1117", fg=TEXT,
                            activebackground="#1d2734", activeforeground=TEXT, bd=0)
        self.menu.add_command(label="Maximize Window", command=self.maximize_window)
        self.menu.add_command(label="Minimize Window", command=self.minimize_window)
        self.menu.add_command(label="Close Window", command=self.close_window)
        self.menu.add_separator()
        self.menu.add_command(label="Close Duplicate Tabs", command=self.clean_tabs)
        self.menu.add_command(label="New Browser Tab", command=self.new_tab)
        self.menu.add_command(label="Read Screen", command=self.read_screen)
        self.menu.add_separator()
        self.menu.add_command(label="Local / Cloud Mode", command=self.toggle_mode)
        self.menu.add_command(label="Toggle Voice Listening", command=self.toggle_listen)
        self.menu.add_command(label="Open Full HUD", command=self.open_hud)
        self.menu.add_separator()
        self.menu.add_command(label="Quit Bubble", command=self.quit)

    # -- drawing -----------------------------------------------------------
    def _draw(self) -> None:
        w, h = self.width, self.height
        c = self.canvas
        c.delete("shape")
        c.configure(width=w, height=h)

        # Soft glow behind the capsule, then the capsule itself.
        c.create_polygon(*rounded_points(2, 2, w - 2, h - 2, (h - 4) / 2 if h < 80 else 22),
                         smooth=True, splinesteps=24, fill="", outline="#0f3a46", width=2,
                         tags="shape")
        c.create_polygon(*rounded_points(5, 4, w - 5, h - 4, (h - 8) / 2 if h < 80 else 19),
                         smooth=True, splinesteps=24, fill=PANEL, outline=EDGE, width=1,
                         tags="shape")

        # Status dot: pulses while idle, solid while busy/listening.
        r = 3.5
        cy = 24 if not self.expanded else 25
        dot = self.accent
        c.create_oval(20 - r, cy - r, 20 + r, cy + r, fill=dot, outline="", tags="shape")
        c.create_oval(20 - r - 4, cy - r - 4, 20 + r + 4, cy + r + 4,
                      outline=dot, width=1, tags="shape")

        c.create_text(38, cy, anchor="w", text="J A R V I S", fill=TEXT,
                      font=self.font_title, tags="shape")

        chip = ("LOCAL" if self.mode == "local" else "CLOUD") + ("" if self.busy else "")
        self._chip(chip, w - 26, cy)

        if not self.expanded:
            c.create_text(w - 96, cy, anchor="e", text=self.status, fill=DIM,
                          font=self.font_small, tags="shape")
            self.reply_label.place_forget()
            self.entry.place_forget()
            return

        # ---- expanded panel ----
        c.create_line(16, 46, w - 16, 46, fill=EDGE, tags="shape")
        c.create_text(18, 60, anchor="w", text=self.status.upper(), fill=DIM,
                      font=self.font_small, tags="shape")
        if self.engine:
            c.create_text(w - 18, 60, anchor="e", text=self.engine, fill=DIM,
                          font=self.font_small, tags="shape")

        self.reply_label.configure(text=self.reply)
        self.reply_label.place(x=18, y=74, width=w - 40, height=94)

        # Quick tools bar
        py = 178
        tools = [
            ("act_max", 18, 76, "🗖 Max", self.maximize_window),
            ("act_min", 100, 76, "🗗 Min", self.minimize_window),
            ("act_tabs", 182, 106, "🗂️ Clean Tabs", self.clean_tabs),
            ("act_screen", 294, 82, "👁️ Screen", self.read_screen),
            ("act_close", 382, 70, "✕ Close", self.close_window),
        ]
        for tag, px, pw, label, cmd in tools:
            c.create_polygon(*rounded_points(px, py, px + pw, py + 22, 11),
                             smooth=True, splinesteps=14, fill="#121924", outline=EDGE,
                             tags=("shape", tag))
            c.create_text(px + pw / 2, py + 11, text=label, fill=TEXT,
                          font=self.font_small, tags=("shape", tag))
            c.tag_bind(tag, "<Button-1>", lambda _e, f=cmd: f())

        # Input row
        row_y = h - 46
        c.create_polygon(*rounded_points(16, row_y, w - 88, row_y + 32, 16),
                         smooth=True, splinesteps=18, fill="#121924", outline=EDGE,
                         tags="shape")
        self.entry.place(x=28, y=row_y + 8, width=w - 124, height=18)

        # Microphone button
        mic_cx = w - 62
        mic_cy = row_y + 16
        mic_r = 15
        mic_fill = "#ff5964" if self.listening else "#16222f"
        mic_edge = "#ff8a92" if self.listening else EDGE
        c.create_oval(mic_cx - mic_r, mic_cy - mic_r, mic_cx + mic_r, mic_cy + mic_r,
                      fill=mic_fill, outline=mic_edge, width=1, tags=("shape", "mic"))
        c.create_text(mic_cx, mic_cy, text="\u25cf" if self.listening else "\U0001f3a4",
                      fill=TEXT, font=self.font_glyph, tags=("shape", "mic"))
        c.tag_bind("mic", "<Button-1>", lambda _e: self.toggle_listen())

        # Send button
        send_cx = w - 26
        send_cy = row_y + 16
        send_r = 15
        c.create_oval(send_cx - send_r, send_cy - send_r, send_cx + send_r, send_cy + send_r,
                      fill="#16222f", outline=EDGE, tags=("shape", "send"))
        c.create_text(send_cx, send_cy - 1, text="\u21b5", fill=ACCENT,
                      font=self.font_glyph, tags=("shape", "send"))
        c.tag_bind("send", "<Button-1>", lambda _e: self._submit(None))

    def _chip(self, text: str, right: float, cy: float) -> None:
        c = self.canvas
        color = GOOD if self.mode == "local" else ACCENT
        pad = 8
        width = self.font_small.measure(text) + pad * 2
        x2 = right
        x1 = x2 - width
        c.create_polygon(*rounded_points(x1, cy - 9, x2, cy + 9, 9), smooth=True,
                         splinesteps=16, fill="", outline=color, width=1, tags=("shape", "chip"))
        c.create_text((x1 + x2) / 2, cy, text=text, fill=color,
                      font=self.font_small, tags=("shape", "chip"))
        c.tag_bind("chip", "<Button-1>", lambda _e: self.toggle_mode())
        self._chip_span = (x1, x2)

    # -- interaction -------------------------------------------------------
    def _press(self, event) -> None:
        self._drag = {"x": event.x_root, "y": event.y_root,
                      "wx": self.root.winfo_x(), "wy": self.root.winfo_y(),
                      "moved": False}

    def _motion(self, event) -> None:
        if not self._drag:
            return
        dx = event.x_root - self._drag["x"]
        dy = event.y_root - self._drag["y"]
        if abs(dx) + abs(dy) > 4:
            self._drag["moved"] = True
            self.x = max(0, min(self.screen_w - self.width, self._drag["wx"] + dx))
            self.root.geometry("+%d+%d" % (self.x, self._drag["wy"] + dy))

    def _release(self, event) -> None:
        moved = bool(self._drag and self._drag.get("moved"))
        self._drag = None
        if moved:
            return
        # Chip click handled by tag_bind
        if hasattr(self, "_chip_span") and self._chip_span[0] <= event.x <= self._chip_span[1] and event.y <= 38:
            return
        if self.expanded and 172 <= event.y <= 206:
            return
        if event.y <= self.height and not self.expanded:
            self.expand()
        elif event.y <= 46 and self.expanded:
            self.collapse()

    def _menu(self, event) -> None:
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def maximize_window(self) -> None:
        def worker() -> None:
            try:
                from . import desktop_input
                res = desktop_input.maximize_window()
                self.ui(lambda: self.set_status(res.get("message") or "Window maximized", ACCENT))
            except Exception as e:
                log("maximize failed: %s" % e)
        threading.Thread(target=worker, daemon=True).start()

    def minimize_window(self) -> None:
        def worker() -> None:
            try:
                from . import desktop_input
                res = desktop_input.minimize_window()
                self.ui(lambda: self.set_status(res.get("message") or "Window minimized", ACCENT))
            except Exception as e:
                log("minimize failed: %s" % e)
        threading.Thread(target=worker, daemon=True).start()

    def close_window(self) -> None:
        def worker() -> None:
            try:
                from . import desktop_input
                res = desktop_input.close_window()
                self.ui(lambda: self.set_status(res.get("message") or "Window closed", ACCENT))
            except Exception as e:
                log("close failed: %s" % e)
        threading.Thread(target=worker, daemon=True).start()

    def clean_tabs(self) -> None:
        self.ask("close duplicate tabs in the browser")

    def new_tab(self) -> None:
        self.ask("open a new browser tab")

    def read_screen(self) -> None:
        self.ask("read my screen")

    # -- geometry animation ------------------------------------------------
    def _animate_to(self, width: int, height: int) -> None:
        if self._anim:
            try:
                self.root.after_cancel(self._anim)
            except Exception:
                pass
            self._anim = None
        start_w, start_h = self.width, self.height
        center = (self.x if self.x is not None else (self.screen_w - self.width) // 2) + start_w / 2
        frames = 10

        def step(i: int) -> None:
            t = i / frames
            # ease out
            e = 1 - (1 - t) ** 3
            self.width = int(start_w + (width - start_w) * e)
            self.height = int(start_h + (height - start_h) * e)
            self.x = int(max(0, min(self.screen_w - self.width, center - self.width / 2)))
            self.root.geometry("%dx%d+%d+%d" % (self.width, self.height, self.x, MARGIN_TOP))
            self._draw()
            if i < frames:
                self._anim = self.root.after(14, lambda: step(i + 1))
            else:
                self.width, self.height = width, height
                self._anim = None
                self._draw()
                if self.expanded:
                    self.entry.focus_set()

        step(0)

    def expand(self) -> None:
        if self.expanded:
            return
        self.expanded = True
        self._animate_to(W_OPEN, H_OPEN)
        self.refresh_mode()

    def collapse(self) -> None:
        if not self.expanded:
            return
        self.expanded = False
        self.entry.place_forget()
        self.reply_label.place_forget()
        self._animate_to(W_COLLAPSED, H_COLLAPSED)

    # -- state -------------------------------------------------------------
    def set_status(self, status: str, accent: Optional[str] = None) -> None:
        self.status = status
        if accent:
            self.accent = accent
        self._draw()

    def refresh_mode(self) -> None:
        def worker() -> None:
            try:
                st = _json("/api/ai", timeout=6)
                mode = str(st.get("mode") or "cloud")
            except Exception:
                mode = None
            if mode and mode != self.mode:
                self.mode = mode
                self.ui(self._draw)

        threading.Thread(target=worker, daemon=True).start()

    def toggle_mode(self) -> None:
        target = "cloud" if self.mode == "local" else "local"

        def worker() -> None:
            try:
                st = _json("/api/ai", {"mode": target}, timeout=15)
                self.mode = str(st.get("mode") or target)
                ready = st.get("ready")
                self.ui(lambda: self.set_status(
                    "%s mode" % self.mode, GOOD if self.mode == "local" else ACCENT))
                self.ui(self._draw)
                log("mode -> %s (ready=%s)" % (self.mode, ready))
            except Exception as exc:
                self.ui(lambda: self.set_status("mode switch failed", BAD))
                log("mode switch failed: %s" % exc)

        threading.Thread(target=worker, daemon=True).start()

    def _pulse_loop(self) -> None:
        if not self.busy and not self.listening and not self.expanded:
            self._pulse = (self._pulse + 1) % 2
            self.accent = ACCENT if self._pulse else "#2f8ea8"
            self._draw()
        self.root.after(900, self._pulse_loop)

    def ui(self, fn) -> None:
        """Run something on the Tk thread from a worker."""
        try:
            self.root.after(0, fn)
        except Exception:
            pass

    # -- asking ------------------------------------------------------------
    def _submit(self, _event=None) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.ask(text)

    def ask(self, text: str) -> None:
        if self.busy:
            self.set_status("still working…", WARN)
            return
        self.busy = True
        self.accent = WARN
        self.set_status("thinking…", WARN)
        log("ask: %s" % text)

        def worker() -> None:
            started = time.time()
            try:
                res = _json("/api/command", {"text": text}, timeout=240)
                reply = res.get("reply") or {}
                speech = str(reply.get("speech") or "").strip()
                engine = str(res.get("engine") or reply.get("engine") or "")
                ms = int((time.time() - started) * 1000)
                self.engine = "%s · %.2fs" % (engine, ms / 1000) if engine else ""
                self.reply = speech or "(no answer)"
                self.ui(self._draw)
                if speech:
                    self.speak(speech)
                self.ui(lambda: self.set_status("ready", ACCENT))
            except Exception as exc:
                self.reply = "I could not reach the daemon, sir: %s" % exc
                self.ui(lambda: self.set_status("daemon unreachable", BAD))
                self.ui(self._draw)
                log("command failed: %s" % exc)
            finally:
                self.busy = False
                self.ui(self.refresh_mode)

        threading.Thread(target=worker, daemon=True).start()

    def speak(self, text: str) -> None:
        try:
            import sounddevice as sd
            import soundfile as sf

            url = DAEMON + "/api/tts?agent=jarvis&text=" + urllib.parse.quote(text)
            with urllib.request.urlopen(url, timeout=120) as response:
                raw = response.read()
            data, rate = sf.read(io.BytesIO(raw), dtype="float32")
            sd.stop()
            sd.play(data, rate)
            sd.wait()
        except Exception as exc:
            log("speech failed: %s" % exc)

    # -- voice -------------------------------------------------------------
    def toggle_listen(self) -> None:
        if self.listening:
            self.stop_listening()
        else:
            self.start_listening()

    def start_listening(self) -> None:
        if self.listening:
            return
        self.listening = True
        self.accent = "#ff5964"
        self.set_status("listening — speak", "#ff5964")
        self._voice_thread = threading.Thread(target=self._voice_loop, daemon=True)
        self._voice_thread.start()

    def stop_listening(self) -> None:
        if not self.listening:
            return
        self.listening = False
        self.accent = ACCENT
        self.set_status("microphone off", ACCENT)

    def _voice_loop(self) -> None:
        from . import audio_in

        while self.listening:
            try:
                clip = audio_in.record_smart(
                    silence_duration=float(jsettings.get("silence_ms", 800)) / 1000.0,
                    min_speech_duration=float(jsettings.get("min_clip_sec", 0.3)),
                    max_duration=float(jsettings.get("max_clip_sec", 15)),
                )
            except Exception as exc:
                log("record failed: %s" % exc)
                self.ui(lambda: self.set_status("microphone error", BAD))
                time.sleep(1.0)
                continue
            if not self.listening:
                break
            if clip is None or getattr(clip, "size", 0) == 0:
                continue
            text = self._transcribe(clip)
            if not text:
                continue
            log("heard: %s" % text)
            self.ui(lambda: self.set_status("heard: " + text[:38], WARN))
            # ask() speaks synchronously inside its worker, so the next record
            # starts only after the answer has finished playing.
            self._ask_and_wait(text)

    def _ask_and_wait(self, text: str) -> None:
        started = time.time()
        try:
            res = _json("/api/command", {"text": text}, timeout=240)
            reply = res.get("reply") or {}
            speech = str(reply.get("speech") or "").strip()
            engine = str(res.get("engine") or reply.get("engine") or "")
            ms = int((time.time() - started) * 1000)
            self.engine = "%s · %.2fs" % (engine, ms / 1000) if engine else ""
            self.reply = speech or "(no answer)"
            self.ui(self._draw)
            if speech:
                self.ui(lambda: self.set_status("speaking…", ACCENT))
                self.speak(speech)
        except Exception as exc:
            log("voice command failed: %s" % exc)
            self.ui(lambda: self.set_status("daemon unreachable", BAD))
        finally:
            if self.listening:
                self.ui(lambda: self.set_status("listening — speak", "#ff5964"))

    def _transcribe(self, clip) -> str:
        try:
            import soundfile as sf

            buf = io.BytesIO()
            sf.write(buf, clip, 16000, format="WAV", subtype="PCM_16")
            detail = _post_audio("/api/stt", buf.getvalue())
            return str(detail.get("text") or "").strip()
        except Exception as exc:
            log("stt failed: %s" % exc)
            return ""

    # -- misc --------------------------------------------------------------
    def open_hud(self) -> None:
        import webbrowser

        webbrowser.open(DAEMON + "/")

    def quit(self) -> None:
        self.listening = False
        try:
            jsettings.set("bubble_enabled", False)
        except Exception:
            pass
        try:
            if self._lock:
                self._lock.close()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass


def main() -> int:
    # One bubble per desktop: the port stays bound for the life of the process.
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", LOCK_PORT))
        lock.listen(1)
    except OSError:
        print("JARVIS bubble is already running.")
        return 0

    if not daemon_up():
        print("JARVIS daemon is not answering on %s - start it first." % DAEMON)
        return 1

    try:
        root = tk.Tk()
    except Exception as exc:
        log("tkinter failed: %s" % exc)
        print("Could not open a window: %s" % exc)
        return 1

    bubble = Bubble(root)
    bubble._lock = lock
    if "--expanded" in sys.argv[1:]:
        root.after(500, bubble.expand)
    try:
        jsettings.set("bubble_enabled", True)
    except Exception:
        pass
    log("bubble started (daemon %s)" % DAEMON)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            lock.close()
        except Exception:
            pass
        log("bubble exited")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log("fatal: " + traceback.format_exc())
        raise
