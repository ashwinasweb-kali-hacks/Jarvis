# JARVIS-OS

> A fan-made, local-first AI assistant OS in the spirit of Tony Stark's workshop.

JARVIS-OS replaces the desktop with a voice-first holographic HUD: floating cyan
glass panels, a Three.js quantum-core hologram, WebXR support for standalone
headsets (Meta Quest 3), a local speech pipeline, and a brain that answers from
free cloud models **or** a fully offline GGUF model.

No kernel hacks. It runs on a stock Linux kernel with a kiosk compositor, and the
Python daemon does all the thinking.

---

## What works today

| Area | Status |
|---|---|
| Mic → silence detection → Groq Whisper STT (local fallback) | ✅ |
| Spoken acknowledgements (CC BY-NC voice pack) | ✅ |
| HUD shell: panels, telemetry, log, arc-reactor orb | ✅ |
| Three.js workshop scene (bike, car, quantum core, nebula) | ✅ |
| WebXR / Meta Quest 3 (AR passthrough, hit-test, anchors, hand tracking) | ✅ |
| Quest USB link over `adb reverse` (no certificate warning) | ✅ |
| Typed command box (reliable fallback for voice) | ✅ |
| Brain with 5-tier fallback chain (Groq chat first) | ✅ |
| Local mode: Ollama brain + local Whisper + local TTS, 100% offline | ✅ |
| Live conversation (click once, auto-resumes listening) + live vision | ✅ |
| Conversational PC control: apps, files, windows, browser tabs | ✅ |
| Dynamic Island popup bubble (separate always-on-top process) | ✅ |
| Live search answers (DuckDuckGo lite, spoken, not just a web page) | ✅ |
| EDITH-style AR console panel (transcript, state, pinned surface) | ✅ |
| Phone panel + GlobalFone adapter (OS dialer fallback) | ✅ |
| MCP server (`jarvis-workshop`, 17 tools) | ✅ |
| Bootable ISO + GRUB + DRM compositor | 🧪 experimental |
| Wake word, gestures, installer | ⬜ planned |

Full roadmap: [`docs/JARVIS-OS-STAGES.md`](docs/JARVIS-OS-STAGES.md).

---

## Quick start (Windows)

```powershell
git clone https://github.com/ashwinasweb-kali-hacks/Jarvis.git
cd JARVIS-OS
py -3 -m venv .venv
.venv\Scripts\python.exe -m ensurepip --upgrade
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m jarvis.daemon
```

Then open <http://127.0.0.1:8765/>.

### Linux / macOS

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m jarvis.daemon
```

Optional extras (TTS, audio players, local GGUF): `requirements-optional.txt`.
The default voice out is `edge-tts` (free neural voices, needs internet); set
`JARVIS_TTS_MODEL=piper` (or `pyttsx3`) for fully offline speech.

Speech in defaults to **Groq Whisper large-v3-turbo** (low latency, needs a free
`GROQ_API_KEY`; the daemon reads it from `~/.jarvis/keys.json` or the environment)
and falls back to the local `faster-whisper` model automatically. Force a local
engine with `JARVIS_STT_MODEL=faster-whisper-small.en`.

### Giving the assistant eyes

Say **"what do you see"**, press **👁 WHAT DO YOU SEE?** in the VOICE TEST panel, or let JARVIS
scan the room. The page grabs a frame from **the device's own camera** (on the Quest 3 that is the
Quest's camera), the daemon sends it to **Gemini** (native `generateContent` with the image inline,
falling back to Groq's multimodal `qwen/qwen3.8-27b`), and the description is spoken back and shown
on the AR panel.

Inside an **active AR session** WebXR owns the camera, so the app uses the **WebXR Raw Camera
Access** API (`XRWebGLBinding.getCameraImage`) to read the passthrough camera itself. The VOICE
TEST panel reports exactly where you stand:

| Chip | Meaning |
|---|---|
| `AR camera API present (enter AR to activate)` | the browser knows the API; it activates with a session |
| `AR camera readable (raw access live)` | the passthrough camera can be read - the assistant sees what you see |
| `AR camera not readable in this session` | this browser does not expose the passthrough to pages |

> If Quest Browser does not ship Raw Camera Access, **no web page** can read the passthrough
> camera - that is a platform limit, and only a native Quest app can do it. The app tells you the
> truth either way instead of pretending.

### The brain

**Gemini 3.5 Flash is the primary brain.** Answers come from the fastest
backend that is actually available:

| Order | Backend | Notes |
|---|---|---|
| 1 | Claude OAuth | if a token is stored |
| 2 | **Gemini 3.5 Flash** | `gemini-3.5-flash`, ~1-2 s answers |
| 3 | Gemini 3.5 / 3.1 Flash Lite, 3 Flash Preview, 2.5 Flash | the free tier meters **20 requests/day per model**, so the chain stacks the daily budget |
| 4 | Groq chat (`openai/gpt-oss-120b`) | ~0.7 s, shares the STT key |
| 5 | OpenCode CLI | local `opencode-cli.exe`, model `opencode/minimax-m3.1-flash-free` |
| 6 | OpenJarvis / GPT4All / Ollama | optional, only if installed |
| 7 | offline stub | canned replies, always works |

Gemini 3.x is a *thinking* model, so the client sends `reasoning_effort: none`
to skip the reasoning phase (that alone takes the answer from ~4 s to ~1 s).
The free tier allows **20 requests per day per model**, so when Gemini 3.5
runs out the client records a cooldown and automatically continues with
`gemini-2.5-flash` instead of failing.

Keys live in the key vault (`~/.jarvis/keys.json`): provider `gemini` (env
`GEMINI_API_KEY`) and provider `groq` (env `GROQ_API_KEY`).

The active backends show up in the **VOICE TEST** panel and in
`GET /api/health` under `brain` (including any quota cooldowns). Override the
hosted model with `JARVIS_GEMINI_MODEL`, the local model with
`JARVIS_ACTIVE_MODEL`.

### Testing the brain, TTS and STT from the HUD

Open the **VOICE TEST** panel (dock button, or say *"voice test"*). It is
test-only - nothing it does changes your settings or saves audio.

| Block | What it does |
|---|---|
| TEXT TO SPEECH | plays a sample through the daemon (edge-tts) |
| SPEECH TO TEXT | records 5 s in the browser, sends the WAV, prints the transcript + engine |
| FULL LOOP (NO MIC) | TTS → decode → STT, so both engines are checked without a mic |
| **BRAIN (AI MODEL)** | asks the model and reports the answer, the engine and the latency; **SPEAK THE REPLY** reads it back |
| **FULL ASSISTANT** | mic → STT → brain → TTS in one click - the exact path the headset uses |

`GET /api/command` returns `engine` and `elapsed_ms` next to the reply, so the
HUD can always show which model answered.

### Headset (Meta Quest 3)

Standalone browsers only allow WebXR over HTTPS. Use the VR launcher, accept the
self-signed certificate once, then open `https://<your-lan-ip>:8765/`:

```powershell
.\run-jarvis-vr.bat
```

The launcher prints the headset URL and, if `adb` is on PATH, runs
`adb reverse tcp:8765 tcp:8765` so `http://localhost:8765/` also works over USB
without a certificate warning. Allow inbound TCP 8765 in Windows Firewall
(admin PowerShell):

```powershell
netsh advfirewall firewall add rule name="JARVIS Daemon 8765" dir=in action=allow protocol=TCP localport=8765
```

In the headset: press **🥽 AR MODE** to enter Quest 3 passthrough (`immersive-ar`),
or **🥽 VR MODE** if AR is unavailable. A headset browser is detected automatically and offers an
**ENTER AR MODE** overlay, because WebXR needs a user gesture. Inside a session **trigger = speak**,
**grip = pin/unpin the holographic panel**; with hand tracking a **pinch** is the
trigger, so voice works without controllers. The panel snaps to detected surfaces
via WebXR hit-testing and remembers where you pinned it, so it reappears there on
the next AR session (say `unpin panel` or grip again to release it). Voice commands
`pin panel`, `unpin panel`, `ar mode` and `exit vr` work too.

### USB instead of Wi-Fi (no certificate warnings)

With Developer Mode on and the Quest plugged in:

```powershell
.\run-jarvis.bat          # plain http daemon
.\connect-quest.bat       # adb reverse + opens the page in the headset
```

`connect-quest.bat` finds `adb` (PATH, Android SDK, or SideQuest), waits up to
90 s for the headset, checks the device is authorised, runs
`adb reverse tcp:8765 tcp:8765` and launches `http://localhost:8765/` inside the
headset. `http://localhost` is a secure context, so WebXR works with no
certificate prompt. Re-run it after unplugging.

`adb` is already installed on this PC at
`%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe` and that folder is on the
user PATH. `scrcpy` is installed as well, so you can mirror the headset screen
to the PC while debugging WebXR:

```powershell
scrcpy            # needs the headset in the Quest Home > Developer mode
```

#### Checking the link from inside the HUD

The **VOICE TEST** panel reports the headset link next to the XR chips:

| Chip | Meaning |
|---|---|
| `adb ready - no headset attached` | `adb` works, nothing is plugged in |
| `Quest <serial> connected` | the headset is authorised and visible |
| `adb reverse 8765 active` | the tunnel to this daemon is open |
| `adb reverse not set (run connect-quest.bat)` | run the script to open it |

The same data is available from `GET /api/health` under `quest`.

#### What the AR panel shows

The floating panel is a small console, not a blank hologram:

| Element | Meaning |
|---|---|
| `J.A.R.V.I.S.` | the active agent (jarvis / friday / edith / ultron) |
| `LISTENING` / `SPEAKING` / `STANDING BY` | live mic + TTS state |
| `YOU ...` | the last thing you said, as transcribed by Groq |
| the reply | JARVIS's answer, typed out |
| `TRIGGER = speak  GRIP = pin panel` | controls, plus the clock |

Trigger is real push-to-talk in XR: pressing it starts the recorder, releasing it
stops and transcribes. With hand tracking a pinch does the same, so no
controllers are needed.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Shell — HUD panels, orb, Three.js holograms, WebXR      │  what you see
├──────────────────────────────────────────────────────────┤
│  Daemon — voice → brain → tools → UI commands (port 8765)│  the only "user"
├──────────────────────────────────────────────────────────┤
│  Wayland/DRM compositor in kiosk mode (no desktop)       │
├──────────────────────────────────────────────────────────┤
│  systemd + minimal base distro                           │
├──────────────────────────────────────────────────────────┤
│  Stock Linux kernel                                      │
└──────────────────────────────────────────────────────────┘
```

The shell never decides anything on its own — it obeys UI commands from the
daemon (`open_panel`, `close_panel`, `hologram`, `arrange`, `focus`).

---

## The brain

`jarvis/brain.py` exposes one function: `respond(text, context) -> Reply`
(spoken text + optional structured actions). The provider chain, in order:

1. **9Router / OpenCode CLI** — free models through a local gateway
   (`9router/free-auto` → DeepSeek → GLM → MiMo, plus Groq GPT-OSS 120B).
2. **Direct Gemini API** — `gemini-3.8-flash` (needs `GEMINI_API_KEY`).
3. **OpenJarvis** — optional local agent source tree.
4. **Local GGUF** — `gpt4all` + any chat-tuned `.gguf` (fully offline, no key).
5. **Deterministic stub** — 0-token keyword engine, always answers.

Every tier is optional. With no network at all, tier 4 or 5 still replies, so
JARVIS never dies on a dead API.

### Local / Cloud mode

The HUD carries a `LOCAL` / `CLOUD` switch next to `BRAIN` and `GEMINI` in the
CONTROL DECK (and the same choice by voice: *"switch to local mode"*, *"are you
local"*). The mode is stored as `ai_mode` in `~/.jarvis/settings.json`.

| Mode | Answers with | Cost |
|---|---|---|
| `cloud` (default) | the Gemini → Groq → OpenCode CLI chain above, unchanged | Gemini quota |
| `local` | `qwen3.5:4b` for words, `gemma3:4b` for eyes, through Ollama on this PC (`E:\JARVIS\ollama`) | nothing, fully offline |

Local mode makes **no** cloud request. If Ollama is down or the model is missing
the answer is *"Local mode is selected and the local model is unavailable, sir:
… I will not switch to the cloud on my own."* (`engine: local-unavailable`) —
the mode never changes itself.

Service: `E:\JARVIS\start-ollama.ps1` / `E:\JARVIS\stop-ollama.ps1`. The model
stays resident (`keep_alive` 30m) and runs on the GPU, so a spoken answer takes
~0.4–0.7 s. `"think": false` is sent because Qwen3.5 otherwise spends the whole
token budget on hidden reasoning and returns empty content.

**100% Offline Voice Conversation**:
In `LOCAL` mode, the entire voice pipeline is on-device with zero internet needed:
- **STT**: `faster-whisper` (`small.en`, `base.en`) loads directly from `E:\JARVIS\models\whisper` with 0 cloud calls (no Groq delay or timeout).
- **LLM**: Ollama (`qwen3.5:4b` for text, `gemma3:4b` for vision) runs on local GPU.
- **TTS**: `pyttsx3` synthesizes speech directly on-device in ~300 ms (no Microsoft cloud `edge-tts` needed).
If you disconnect Wi-Fi or unplug Ethernet, live conversation continues to work smoothly without hanging on "THINKING...".

**Local eyes.** `gemma3:4b` (2.9 GB, also on E:) is the local vision model:
`ollama pull gemma3:4b`. A 6 GB card holds one 4B model at a time, so a visual
turn is a single call to `gemma3:4b` (frame + question → description + answer)
and text turns stay on it for 90 s afterwards, which avoids 6–10 s model swaps
mid-conversation. Visual turn ≈2–3 s; the engine label names the model that
actually answered.

### Live video conversation

Click **LIVE VISION** in the CONTROL DECK (or say *"live vision on"*). The camera
stream opens once; every spoken or typed question then carries one fresh 768 px
frame, so *"what do you see?"*, *"what is this?"* or *"read this label"* answer
about what is in front of you right now. With `LOCAL` selected the whole turn
(frame → answer → speech) stays on this machine; with `CLOUD` the frame and the
question go to Gemini in one call. `"live vision off"` closes the camera.

> In a Quest AR session the headset camera belongs to WebXR: the page uses Raw
> Camera Access when the browser exposes it, otherwise the device camera the
> browser allows. A web page cannot read passthrough without `getCameraImage`.


### Screen, mouse, keyboard, apps

`read my screen` / `what is on my screen` reads the focused window with UI
Automation plus Windows OCR — local, ~0.3–0.9 s, no quota. `click save`,
`press ctrl s`, `type hello`, `scroll down`, `switch to notepad`, `install
7zip.7zip`, `uninstall spotify`, `run powershell Get-Date`, `browser search for
…`, `what is on my calendar`, `read my email` are all parsed locally and run on
the host.

**Full browser control via conversation**:
*"open a new tab"*, *"open tab for github.com"*, *"close this tab"*,
*"close duplicate tabs in the browser"*, *"list all open tabs"*,
*"switch to tab 2"*, *"refresh the page"*, *"go back"*, *"go forward"*.

**Windows UI window management via conversation**:
*"maximize this window"*, *"can you please maximize my browser"*,
*"minimize this window"*, *"minimize all windows"*, *"restore the window"*,
*"close this window"*.

**Live web search & answer**:
When you say *"search for the current president in usa"* or *"look up the latest news on X"*,
JARVIS fetches live DuckDuckGo web results, passes the snippets to the active
model (Ollama Qwen3.5 4B when `LOCAL`, Gemini when `CLOUD`), and speaks and displays
the direct factual answer (e.g. Donald Trump as 47th president) instead of just
opening an empty search engine page.

Anything irreversible (delete, uninstall, shutdown, dangerous
PowerShell) is parked and needs an explicit *"confirm"*.

`GET /api/ai` (mode + live status, `POST` to switch), `POST /api/screen`
(describe / read / click / vision / screenshot), `POST /api/browser`,
`POST /api/workflow`, `POST /api/approve` (confirm / cancel), `POST /api/email`.

### Dynamic Island popup bubble

A floating, frameless capsule at the top centre of the laptop screen, styled after
the MacBook Dynamic Island:

- **Always on top & works in the background**: runs as its own lightweight process
  (`pythonw -m jarvis.bubble`), so you can minimize the browser and still talk to
  JARVIS while doing work in other apps.
- **Collapsed**: sleek status pill showing the pulsing cyan/green core dot,
  `J A R V I S`, connection state, and active `LOCAL`/`CLOUD` mode badge.
- **Expanded** (click/tap): expands smoothly into an interactive panel with live
  status, assistant spoken reply, quick action tools (`[🗖 Max]`, `[🗗 Min]`,
  `[🗂️ Clean Tabs]`, `[👁️ Screen]`, `[✕ Close]`), text entry, and a live microphone toggle for
  instant voice interactions.
- **One-click Mode Switch**: click the `LOCAL`/`CLOUD` pill to switch modes instantly.
- **Voice control**: say *"open bubble"*, *"show dynamic island"*, *"close bubble"*,
  or click `🏝️ BUBBLE` in the CONTROL DECK drawer.
- **API**: `GET /api/bubble` (status), `POST /api/bubble` (`{"action": "start"|"stop"|"toggle"}`).

### Configuration

All settings are environment-overridable (see `jarvis/config.py`):

| Variable | Default | Meaning |
|---|---|---|
| `JARVIS_MODEL` | `small.en` | Raw faster-whisper size (`tiny`…`large-v3`) |
| `JARVIS_STT_MODEL` | `groq-whisper-large-v3-turbo` | STT model id from `jarvis/voice_models.py` |
| `JARVIS_TTS_MODEL` | `edge-tts` | TTS engine id (`edge-tts`, `piper`, `kokoro`, `pyttsx3`) |
| `JARVIS_PIPER_VOICE` | `~/.jarvis/voices/<voice>.onnx` | Piper voice file for offline TTS |
| `JARVIS_INPUT_DEVICE` | system default | Mic device index (`--list-devices`) |
| `JARVIS_SILENCE_MS` | `770` | Silence before the recording stops |
| `JARVIS_MAX_RECORD_MS` | `15000` | Hard recording cap |
| `JARVIS_TLS` | `0` | `1` enables HTTPS (required for WebXR) |
| `JARVIS_MODE` | `stub` | `stub` / `local` / `cloud` |
| `JARVIS_GLOBALFONE_URL` | — | GlobalFone gateway endpoint |
| `JARVIS_SETTING_AI_MODE` | `cloud` | `local` (Ollama/Qwen3.5) or `cloud` (Gemini) |
| `JARVIS_OLLAMA_URL` | `http://127.0.0.1:11434` | Local Ollama endpoint |
| `JARVIS_OLLAMA_MODEL` | `qwen3.5:4b` | Local text model tag |
| `JARVIS_OLLAMA_VISION_MODEL` | `gemma3:4b` | Local eyes (multimodal model) |
| `JARVIS_OLLAMA_DIR` | `E:\JARVIS\ollama` | Where Ollama and its models live |

API keys live in `~/.jarvis/keys.json` (never in the repo) or in environment
variables. Use the in-app **API Keys** panel or `set_api_key` over MCP.

---

## Phone

`📞 PHONE` opens a floating 12-key dialer. `CALL` sends
`call <number> via globalfone` to the brain, which invokes the `globalfone_call`
tool. If `JARVIS_GLOBALFONE_URL` and a vault token are configured it uses the
GlobalFone gateway; otherwise it falls back to the OS `tel:` handler and says so.

---

## Testing

```powershell
.venv\Scripts\python.exe -m pytest -q
```

The suite is headless: no mic, speakers, GPU or network needed.
Silence detection, hallucination filtering, config overrides, the permission
gate and the daemon dispatch are all covered with mocks.

**63 passed, 3 skipped.**

Manual checks the owner must do (a machine cannot hear or see):

- Speak a short and a long sentence; both should be transcribed.
- Stay silent; no acknowledgement should play.
- Ask "what time is it" and hear a spoken reply.
- Put on the Quest 3 and confirm the HUD renders at a smooth frame rate.

---

## Safety

- Tools are allow-listed with a `safe` / `confirm` / `blocked` risk level.
- Destructive actions (delete, uninstall, shutdown, kill process, empty recycle
  bin, dangerous PowerShell) are parked in `jarvis/approvals.py`: JARVIS says
  what it is about to do and only an explicit **"confirm"** / **"yes"** runs it.
  "no" / "cancel" or 120 s of silence drops it. Workflows use the same gate.
- No success is claimed without verification: `winget` installs are checked with
  `winget list`, local answers carry `engine: local:qwen3.5:4b` or
  `local-unavailable`, and host actions are reported from their real result.
- Screen reading is local (UI Automation + Windows OCR); the vision model is
  only called when explicitly asked.
- Every action is appended to `~/.jarvis/actions.log`.
- LLM output is never passed to a shell; tools take validated arguments.
- No secrets are committed; `gateway/` and key files are gitignored.

---

## Licensing and credits

This is a **non-commercial fan project**. Iron Man, JARVIS and Stark Industries
are Marvel/Disney property; no film assets are shipped here.

| Asset | Licence | Notes |
|---|---|---|
| `assets/openpeon-jarvis/` voice lines | **CC BY-NC 4.0** | Credit retained. Non-commercial use only. Replace before any wider release. |
| Three.js | MIT | Vendored build in `shell/three.min.js`. |
| Intro music | *not shipped* | Point `JARVIS_INTRO_FILE` at your own file. Do not redistribute copyrighted audio. |
| Hologram models | generated in code | No ripped movie models. |

The workshop reference image is **not** included in this repository.

---

## Project docs

- [`docs/JARVIS-OS-STAGES.md`](docs/JARVIS-OS-STAGES.md) — the full roadmap
- [`PROGRESS.md`](PROGRESS.md) — what is done, what is next
- [`DECISIONS.md`](DECISIONS.md) — every non-obvious choice, with reasons
- [`docs/LOCAL-AI-GATEWAY.md`](docs/LOCAL-AI-GATEWAY.md) — gateway runbook
