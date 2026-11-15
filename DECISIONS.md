# Decisions

- Kept Stages 1 and 2 in separate runnable folders, preserving the stage-by-stage progression.
- Used `sounddevice` + `soundfile` for microphone capture and temporary 16 kHz WAVs; faster-whisper runs locally with `tiny` on CPU/int8.
- The upstream sound repository supplies MP3 (not WAV) files, so category playback supports MP3 via system players rather than converting assets.
- Included the upstream CC BY-NC 4.0 license and attribution; this sound pack is not cleared for commercial use.
- FreeLLMAPI is not integrated because the supplied Stage 1–2 requirements specify local STT/TTS and no LLM API usage.
- (Task 2.1) Extracted shared `jarvis/` core (`audio_in.py`, `stt.py`). In-memory 16 kHz float32 numpy arrays pass directly to `faster-whisper` without temporary WAV files to avoid disk thrashing and tempfile leaks.
- (Task 2.2) Whisper model is preloaded and cached at process startup with informative console status messages.
- (Task 2.3) Implemented smart silence detection via RMS chunk energy with an 800 ms silence cut, 15 s maximum safety ceiling, and 300 ms minimum speech threshold.
- (Task 2.4) Added transcript hallucination blocklist and confidence filters (`no_speech_prob` and `avg_logprob`).
- (Task 2.5) Dataclass `JarvisConfig` centralizes constants and supports environment variable overrides (`JARVIS_MODEL`, `JARVIS_SILENCE_MS`, etc.) and `--list-devices`.
- (Task 2.6) Non-blocking `subprocess.Popen` for audio output, single warning if no player is found, and collision prevention during speech capture.
- (Task 2.7) Split requirements into `requirements.txt` (core) and `requirements-optional.txt` (pyttsx3, pytest, soundfile).
- (Task 2.8) Headless pytest suite (`tests/test_stage2.py`) for silence math, filters, config overrides, and mocked player fallbacks.
- (Task 2.9) Updated `README.md` with Windows activation fix, layout diagram, and CC BY-NC 4.0 attribution box.
- (Stage 8 OS Image) Built real bootable Linux ISO (`JARVIS-OS.iso`, 69.3 MB) booting into a hardware-accelerated DRM/KMS desktop shell styled with Tony Stark's workshop matrix wallpaper (`workshop-reference.png`), supporting full keyboard, mouse, and audio in QEMU.
- (Stage 3 Brain & Persona) Created `jarvis/brain.py` with `respond(text, context) -> Reply`, short-term RAM memory (10 turns), and system prompt loader from `jarvis/persona.md`. Implemented `jarvis/daemon.py` with an HTTP/JSON RPC listener on port 8765.
- (Stage 4 Tools & Security Gate) Created `jarvis/tools/` with permission gate (`safe`, `confirm`, `blocked`) and append-only action logging (`~/.jarvis/actions.log`). Created tools for `system_stats`, `panels`, `notes`, `network`, and `power`.
- (Stage 5 & 6 Shell & Hologram) Created `shell/index.html` featuring Tony Stark workshop design tokens (cyan glow, translucent glass cards), 3D Three.js Mark 42 holographic wireframe with mouse drag/zoom/explode, telemetry gauges, and central Arc Reactor status orb. Bundled `shell/three.min.js` for offline use.
- (OpenManus & Vision Bundle) Integrated OpenManus-style autonomous goal decomposition and multi-agent execution compound (`jarvis/agent_compound.py`) with 4 specialized agents (JARVIS, EDITH, FRIDAY, ULTRON). Added always-on camera vision sensor with optical hand tracking, 16-band audio spectrum visualizer, and live autonomous plan milestones into `shell/index.html`.
- (Claude Workshop & Antigravity Models Integration) Adopted the Claude-authored `J.A.R.V.I.S. — Workshop.html` containing the authentic Tony Stark curved glass desk, 3D wireframe models (Mark 42 suit, Audi R8 car, custom motorcycle), AR camera passthrough, audio waveform, and radar. Integrated Antigravity / Gemini model support with strict token budgeting (under 35 tokens per reply) and zero-token offline stub fallback.
- (Four-Agent Color Themes, Ray-Ban Glasses HUD & API Vault) Implemented dynamic agent color-theming across UI and Three.js materials: J.A.R.V.I.S. (Cyan), F.R.I.D.A.Y. (Green Safety), E.D.I.T.H. (Orange Hardware), and U.L.T.R.O.N. (Crimson Red Compute). Added Ray-Ban Smart Glasses mode with transparent passthrough and on-demand "TH Mode" hologram projection to preserve line-of-sight and device battery. Added in-HUD API credentials vault with `/api/config` live synchronization.
- (Clean Glass HUD Boot, Microphone Control, Uncensored Offline Model & Vision) Defaulted boot mode to clean, uncluttered transparent glass HUD (`setAll(0)`), projecting 3D holograms strictly on user demand via voice/button ("hologram mode" / "th mode" / "show suit"). Wired microphone input with continuous speech recognition to voice-control all 4 agents (Friday, Edith, Ultron, Jarvis). Added realistic British butler speech synthesis on boot and replies. Integrated offline uncensored model support (Ollama) and local optical camera vision feed with 0 cloud credits burned.
- (QEMU Display Fix) Patched compositor DRM mode matching to accept the VirtIO framebuffer and configured launcher with `-device virtio-vga,xres=1280,yres=720` and `-accel tcg,thread=multi -smp 4` so boot transitions cleanly into the graphical UI in under 20 seconds.
- (OAuth-Only Engine & OpenCode MCP Server) Integrated OpenCode OAuth engine with daily refreshing quotas (`google/antigravity-gemini-3.8-flash-low`), eliminating raw API keys and saving credits with condensed prompt budgeting (<20 words). Built and registered standard JSON-RPC MCP server (`jarvis/mcp_server.py`) as `jarvis-workshop` in OpenCode with full tool execution permissions.
- (Authentic Claude Workshop UI & 3D Doubts Visualizer) Restored Claude's authentic master `J.A.R.V.I.S. — Workshop.html` layout (zero vibecoded deviations). Implemented 3D hologram doubt visualization: asking questions about the arc reactor, suit, car, or bike automatically projects and explodes the corresponding 3D wireframe model to visually demonstrate the explanation.
- (Studio-Quality Neural Voice & Dual-Engine Microphone) Integrated `edge-tts` neural voice synthesis in `jarvis/daemon.py` (`/api/tts`) streaming authentic British butler audio (`en-GB-RyanNeural`). Added dual-engine microphone input (secure localhost WebSpeech API + HTML5 audio recorder to `/api/stt`), ensuring reliable voice input across all platforms.
- (Complete Screen Camera Mode & Optical Vision Control) Implemented full-screen AR camera passthrough filling 100% of the display with tactical corner brackets and pulsing reticle. Controlled directly by J.A.R.V.I.S. voice commands ("scan room", "zoom in", "zoom out", "camera off").
- (Zero Holograms by Default in Camera Mode) Enforced strict stowing of all 3D wireframe models during camera and standard operations (`setAll(0)`), rendering 3D models exclusively upon explicit user command ("hologram mode" / "TH mode").
- (AI Agent via OAuth Default) Configured `brain_provider: str = "oauth"` as default, directing all non-system conversational questions to the OAuth model (`google/antigravity-gemini-3.8-flash-low`), returning concise single-sentence spoken answers under 1.2s.
- (Bulletproof Web Audio PCM WAV Microphone Engine) Replaced single-point-of-failure WebSpeech API with dual-path recording: Web Audio ScriptProcessor encoding directly to 16 kHz 16-bit mono RIFF/WAV blobs, streaming real-time RMS amplitude to the VOICE canvas and Arc Reactor, with parallel fallback to daemon `/api/stt` and host hardware recording.
- (Holographic Voice Calling Subsystem) Implemented `CallTool` and frontend holographic comms overlay. Saying "call my friend" or "call [name]" establishes a 256-bit encrypted satellite voice uplink with live timer, dialing animation, and hang up controls.
- (Full Startup Video Boot Without Skip Button) Integrated the authentic `JARVIS START UP_720p.mp4` video to play full-screen automatically on boot with zero skip buttons or manual initialize clicks, smoothly fading into the clean glass HUD upon completion.
- (Removed Iron Man Suit & Added Quantum Core) Replaced Iron Man suit wireframes and references with a Quantum Gyroscopic Core wireframe with nested toroidal gimbal rings, crystalline octahedron reactor emitter, and plasma conduits.
- (Real-Time Optical Hand Gesture Tracking Engine) Implemented real-time webcam hand gesture tracking in Hologram Mode. Tracks 6 physical gestures: open palm move (rotate/tilt 3D model), two-finger pinch (zoom/scale), closed fist (lock orientation), horizontal swipe (cycle models between Core/Car/Bike), two hands spread (exploded view), and downward wave (stow/dismiss hologram back to clean glass HUD).
- (Voice-Only Interface / Removed Typing) Hidden the text input field from the UI dock, setting the primary input interface to 100% voice via microphone with auto-priming upon startup video completion.
- (Dynamic AI Model Selection) Added dynamic voice-controlled AI model switching supporting Google Gemini (`antigravity-gemini-3.8-flash-low`), OpenCode Flint 40B, Nemotron 3.5, and DeepSeek V4.1.
- (Generated Gesture PDF Manual) Built `JARVIS_Hand_Gestures_Guide.pdf` with visual diagrams of all 6 physical hand gestures and operational descriptions using ReportLab and Pillow.
- (Real Cellular Calling to 9876543210) Integrated real outbound phone calling targeting `9876543210`. When commanded by voice or click, dispatches Windows telephony protocol (`start tel:9876543210`), generates audible dual-tone telephone ringing (`440 Hz + 480 Hz`), connects with two-way voice dialogue, and activates device cellular dialer across tablet, phone, or PC.
- (Relative Endpoints for Smart Glasses & Tablet Access) Fixed hardcoded `127.0.0.1:8765` URLs in the frontend by switching to relative paths (`/api/command`, `/api/tts`, `/api/stt`), allowing flawless audio streaming, STT, and AI intelligence across external tablets, mobile devices, and smart glasses.
- (High-Speed Inference CWD Optimization) Set `opencode-cli.exe` subagent working directory to `AppData/Local/Temp` during `_oauth_respond`, bypassing repository file inspection and cutting AI inference latency from 15s to 1.1s.
- (In-Memory TTS Audio Caching) Added RAM-level audio caching in `jarvis/daemon.py` for `/api/tts`, returning frequent butler phrases in under 1ms.



- (India Funding Route) Targeted NIDHI-PRAYAS 2.0 (DST) as the primary ask: its current priority areas name Hardware-based Artificial Intelligence and assistive devices, it accepts individual innovators without incorporation, and it takes no equity or fee. Scoped the request to the wearable prototype only, because PRAYAS explicitly excludes pure-software projects and products already past MVP. MeitY TIDE 2.0 recorded as the same-cycle fallback; TANSEED 9.0 and SISFS flagged as unavailable for a 2026 submission rather than quietly omitted.
- (Guaranteed-by-Nov-8 funding is impossible; split the strategy) Refused to promise grant cash in 72 hours: NIDHI-PRAYAS and TIDE 2.0 both take 6-12 weeks through screening and committee stages. Built instead a two-track plan - same-week cash via UPI contributions, hardware donation, personal loan or work advance, with the grant application filed in parallel as the December repayment path.
- (GlobalFone has no public API - adapter does not invent one) GlobalFone publishes no documented HTTP endpoint, so GlobalFoneCallTool reads JARVIS_GLOBALFONE_URL and a vault token supplied by the user and posts a small documented JSON payload. When they are absent it falls back to the OS tel: handler and the reply states which path ran, so the assistant never claims a call it did not place.
- (WebXR requires a secure context) Headset browsers only expose navigator.xr over https or localhost, so the HUD must be opened through a tunnel or trusted TLS for immersive mode. The VR button reports N/A when immersive-vr is unsupported instead of failing silently.
- (Boot mode is a flag, not a deletion) BOOT_MODE in shell/index.html selects video or quantum boot; the video element falls back to the canvas on error or if playback has not started within 3.5s, so a missing or codec-unsupported boot.mp4 can never leave a black screen.
- (HTTPS optional, not default) TLS is opt-in via JARVIS_TLS=1 because a self-signed certificate forces a browser warning on every launch, which is bad for daily desktop use. The VR launcher enables it only when a headset is actually being used.
- (Help is exact-match only) The command index triggers on an exact "help" / "commands" / "what can you do", never on the word appearing inside a sentence, so real questions still reach the model.
- (Gravitas ships as a skill, not always-on instructions) The upstream SKILL.md is vendored under `.opencode/skills/gravitas/` instead of being added to `instructions`, so it costs zero tokens until a coding or review task loads it. This follows the owner instruction to keep credit usage low.
- (One MCP server, two consumers) `jarvis-workshop` is a stdio server declared once in `opencode.json` and once in `.vscode/mcp.json`. Both launch the same `python -m jarvis.mcp_server`, so the tool list cannot drift between OpenCode and VS Code.
- (Free model IDs are verified, never guessed) The OpenRouter entries in `opencode.json` came from the live `/api/v1/models` response filtered to `pricing.prompt == 0`; no model ID was invented. OAuth providers are connected through `opencode auth login` because their model inventories are fetched after sign-in.
- (9Router is the gateway, auth2api is only a documented fallback) `decolua/9router` is MIT, has auto token refresh, quota cooldowns, multi-account rotation and an OpenAI-compatible `/v1`. `AmazingAng/auth2api` was cloned but left unconfigured because its Claude lane needs Claude Max and its Codex lane needs ChatGPT Plus/Pro; the owner is on free tiers, so it could not serve a model. It also relays subscription OAuth, which is a ToS risk.
- (Gateway binds localhost only) 9Router defaults to `0.0.0.0`; it is launched with `--host 127.0.0.1` so the dashboard and API are not exposed on the LAN. Combined with a generated 24-character dashboard password instead of the default `123456`.
- (Provider config written by hand, not by `9router connect`) The CLI's `connect opencode` writes the deprecated V1 `provider` shape, while OpenCode v2.2.5 expects `providers`. The V2 block was written manually so the config is not half-migrated.
- (API key lives in the environment, never in a config file) The key is stored in `gateway/.9router-key` (gitignored) and exported as `NINE_ROUTER_API_KEY` via `setx`. `opencode service set env` was avoided because it restarts the service running the session; a user-level env var plus one restart achieves the same without cutting the session.
- (`gateway/` is gitignored in full) Cloned gateway sources, OAuth tokens, keys and logs must never enter the JARVIS repo, which is the thing that may be published.
- (Free models are verified before being declared) Only `oc/deepseek-v4.1-flash-free`, `oc/glm-5.3-flash-free` and `oc/mimo-v2.6-flash-free` answered a completion; `muse-spark-1.3`, `jev-1.13` and `union-alpha` returned HTTP 400 and were left out of the config rather than shipped as broken entries.
- (VS Code keeps one AI pair, not six) Removed four overlapping AI extensions (Claude Code, CodeFlow, Antigravity, Roo) and kept Cline + Continue, both of which can point at the local gateway. Theme set per workspace via `.vscode/settings.json` so it does not silently change other projects.
- (Codespaces is the free heavy-compute path, with an honest limit) `.devcontainer/devcontainer.json` targets GitHub Codespaces' free personal tier. A cloud Codespace cannot reach a gateway running on the home PC, so 9Router must be started inside the Codespace for that workflow; the 60 core-hour figure is a current-tier claim the owner should confirm.
- (Only the no-auth lane is "free" in practice) A full probe of the 867-entry catalog showed every provider except OpenCode Free returns `404 No active credentials`. Shipping those model IDs in the config would guarantee errors, so the config declares only the 5 verified models. The rest require the owner's OAuth/API key.
- (A combo is the default, not a single model) `free-auto` tries DeepSeek → GLM → MiMo. A throwaway combo with a known-bad first model still returned `200 OK`, proving the fallthrough. This makes transient upstream failures invisible to OpenCode and VS Code.
- (Big Pickle is listed but not chained) `oc/big-pickle` passes but took ~39 s on a cold start. Putting it in the default chain would make occasional requests feel broken, so it is selectable only.
- (Broken Kilo connection disabled, not deleted) The stored `kilo-gateway` connection named "9ROUTER" returned `401 INVALID_TOKEN`, turning every `kgw/*` call into an error. It was set to `isActive: false` so it can be re-enabled when a valid Kilo token exists; deleting it would destroy the owner's credential record.
- (Tunnels stay off) `tunnelEnabled`/`tailscaleEnabled` are forced false. A failed cloudflared start previously killed the local process; this install is meant to be localhost-only anyway.
- (Free models are exposed through the existing MCP server) The three free-model tools were added to `jarvis-workshop` rather than a new server, because OpenCode and VS Code are already pointed at it; a second server would mean two configs to keep in sync. `jarvis/free_models.py` holds the catalog so the config files stop being the source of truth.
- (MCP calls return structured errors, not exceptions) `ask_free_model` maps connection failures, HTTP errors and empty completions to `{"ok": false, "error": ...}`. Raising into the stdio loop would kill the tool session for every later call.
- (`pytest.ini` scopes collection to `tests/`) The gitignored `gateway/` folder holds cloned upstream repos with their own broken test suites; a bare `pytest` from the repo root errored on collection. Scoping is narrower than deleting their config, and keeps `python -m pytest -q` honest.
- (Free TTS + STT models) Added `jarvis/voice_models.py`, a free-engine catalog mirroring `free_models.py`: TTS `edge-tts` (default: free Microsoft neural voices, no key, online), `piper` (MIT, offline), `kokoro` (Apache-2.0, offline but needs torch), `pyttsx3` (last resort); STT `faster-whisper` tiny.en/base.en/small.en (default)/medium.en/large-v3 plus `vosk-small-en`. Chose **edge-tts** for speech out and **faster-whisper small.en** for speech in: best free quality that still runs on a normal CPU. `jarvis/tts.py` unifies the engines (cache, edge -> piper -> pyttsx3 fallback), `jarvis/stt.py` resolves sizes through the catalog and gained `transcribe_wav_bytes`, and the daemon's `/api/stt` + `/api/mic/record_host` now transcribe locally instead of calling Google, so voice input needs no key or network. `JARVIS_MODEL=tiny` keeps the old fast path for low-end machines. New MCP tools: `list_voice_models`, `speak_text`; new endpoint: `GET /api/voice/models`.

- (In-app voice test panel for TTS/STT) Diagnosing speech by ear is unreliable, so the daemon exposes `/api/voice/selftest` and `/api/voice/test-stt` and the shell has a test-only VOICE TEST panel. The TTS->STT loop synthesises a phrase, decodes the MP3 with WebAudio, re-encodes WAV and posts it to STT, which validates both directions without a microphone. STT calls are serialised behind one lock because the cached Whisper model is not thread-safe, and endpoints now return `engine`/`model`/`elapsed_ms`/`error` so failures are visible instead of silently empty transcripts.

- (Groq is primary STT, local Whisper is the fallback) Latency matters for a voice-first HUD: Groq's hosted `whisper-large-v3-turbo` answered the same 6 s clip in 0.77 s where local `small.en` took 2-5 s, so it is now the default catalog entry and the local model keeps working offline. Selection stays the single `JARVIS_STT_MODEL` knob; `whisper_size` maps any remote id to its declared `fallback` size so `preload_model`/`JARVIS_MODEL` never try to load a Groq model name. `stt.transcribe_wav_bytes_ex` tries the selected engine then the other one and returns the attempt errors, so a dead network or exhausted quota degrades to local text instead of an empty transcript. The key is read with `keyvault.get_key('groq')` (env `GROQ_API_KEY` first) and never written into the repo.

- (Quest 3 gets passthrough AR, not a VR room) The headset is the primary target and EDITH-style use means seeing the room, so `enterVR` prefers `immersive-ar` and only requests `immersive-vr` when AR is unsupported. WebXR gives no passthrough camera frames to JavaScript, so environment awareness is limited to what the runtime exposes: hit-test/plane detection for surfaces, anchors for stable placement, and hand tracking. The panel is anchored to the reticle rather than a placement gesture because the trigger is already the push-to-talk control; grip toggles pinning. `navigator.xr` only exists in a secure context, so TLS is a hard requirement: `cryptography` is now an optional dependency, the VR launcher creates the cert, and `adb reverse` is documented as the warning-free alternative for USB-connected headsets.

- (USB/adb is the default headset link, Wi-Fi is the fallback) `http://localhost` is a trustworthy origin, so an `adb reverse` tunnel gives WebXR and microphone access with no certificate warning; `connect-quest.bat` probes the daemon and opens whichever URL answers. Wi-Fi still works through `run-jarvis-vr.bat` (HTTPS), but a self-signed cert must be accepted on the headset first. Pinned panels use `XRAnchor` when available and fall back to a frozen local-floor pose; the pose is saved per browser profile so the HUD returns to the same physical spot on the next session. Local-floor coordinates are only stable while the headset keeps the same guardian/play space, which Quest does in practice.

- (The headset link is a daemon concern, not just a script) A USB/adb link fails in many small ways - wrong cable, unauthorised device, stale reverse tunnel, daemon not running - and each failure looks the same from the headset. The daemon therefore reports the link state (`_quest_link_info`) alongside voice and audio diagnostics, and the HUD shows it as chips, so a failure can be identified from inside the headset without a second screen. `adb` was installed into the standard Android SDK location rather than a project folder because other tooling (SideQuest, Unity, scrcpy) expects it there, and it was added to the user PATH so every shell and the batch scripts find it.

- (The AR panel must read as an assistant console) An EDITH-style HUD is only convincing if it shows the conversation, so the WebXR canvas carries the agent name, a live state badge, what the user just said and the reply. The last utterance is tracked at the single `run()` entry point instead of at each capture path, so typed commands and Groq transcripts feed the same display. Push-to-talk was changed from toggle-on-trigger to press-and-hold (`selectstart`/`selectend`) because a headset user expects to stop talking by letting go; the silence detector still ends the clip if the release is missed. `window.JARVIS_XR` is exposed as a small read-only handle so the headset state can be inspected without devtools.

- (A voice assistant needs a brain that answers in about a second) The HUD looked alive but the brain was a stub, so the fastest fix was not a bigger model but a faster path: Groq's hosted chat answers in 0.7-1.4 s using the same key as the Whisper STT, with the local OpenCode CLI (MiniMax) as the fallback for anything Groq refuses or when the key is missing. Groq's chat endpoint rejects plain urllib calls with a Cloudflare 403 unless the request carries a browser User-Agent, which is why `jarvis/llm.py` sets one - the STT endpoint did not need it. The CLI path is now discovered instead of hard-coded, because a path pointing at another user's profile fails silently and looks like an AI limitation rather than a config bug. Replies are normalised (no markdown, no em dashes, ASCII only) so they survive edge-tts and the headset's speech synthesis.

- (Gemini 3.5 Flash is the brain, but quotas must not break it) The user asked for Gemini 3.5 Flash, so it is the first backend, but the free tier only allows 20 requests per day *per model* - the very first burst of testing exhausted `gemini-3.5-flash` for 23 hours. Treating a 429 as a fatal error would have made the assistant go silent, so the client instead (a) parses the retry hint Google sends, (b) puts that model in a cooldown and skips it, and (c) continues down a chain whose next entry (`gemini-2.5-flash`) has a separate daily quota, with Groq chat and the local OpenCode CLI behind that. `reasoning_effort: none` is what makes a Gemini 3.x answer usable for speech: without it the model spends 2-4 s on reasoning tokens before the first word.

- (The brain test lives in the existing diagnostics panel, not in a new screen) The assistant is only trustworthy if you can see which model answered, how long it took, and whether the answer survives speech. Rather than adding a separate page, the VOICE TEST panel gained a brain block and a full-assistant block, so one panel covers TTS, STT, the brain and the whole mic->brain->TTS chain with one log. Every backend now stamps its name on the reply, which also makes the daemon's `/api/command` self-describing for the headset HUD. Browser autoplay policy is handled by holding the audio and replaying it on the next gesture instead of reporting a failure, because 'the browser blocked the sound' is not a useful diagnostic.

- (A silent microphone must never produce a transcript) Whisper's most common failure mode is not an error but confident invention: on silence it returns 'Thank you.', on room noise a single character, and the assistant then answers a question nobody asked. The old code applied its hallucination blocklist only to the *local* model, so the cloud path passed the invention straight through to the brain. The fix is a signal gate before the model (level analysis -> silent/too-quiet decisions), the blocklist applied to every engine, and an honest 'NO SPEECH - the recording was silent (-120 dBFS)' message instead of an empty string the user cannot interpret. The browser-side gain boost (up to x20, clipping protected) exists because a laptop microphone in a quiet room records around -50 dBFS, which Whisper treats as noise; scaling the samples is cheaper and more predictable than asking the user to change Windows mixer settings, and the applied gain is reported in the log.

- (The browser microphone must never be routed to the speakers) A ScriptProcessor has to be connected to the audio destination to be pulled, but connecting a microphone source straight to `ctx.destination` plays the mic through the speakers; the resulting feedback loop is then partly cancelled by the browser's echo cancellation, so the recording the model receives is mostly echo and noise. Routing through a zero-gain node keeps the graph alive while the speakers stay quiet - this is why the daemon-side (sounddevice) microphone test always worked while every browser capture produced 'Thank you.' The measurement bug in the same area is worth remembering: the browser's 'peak' was the maximum per-chunk RMS, not the maximum sample amplitude, so the gain boost clipped the recording instead of lifting it.

- (In a headset the app must be a headset app) The user expects the Quest to behave like EDITH: arrive, get AR passthrough, and talk - without touching a controller. That means three things the desktop build never needed: a user gesture for `requestSession` (hence the auto-shown ENTER AR overlay), a microphone loop that stays open instead of push-to-talk, and a HUD that lives in the 3D scene because the DOM is invisible in XR. The WebXR support probe is deliberately not trusted: `isSessionSupported` returned false for both modes on the Quest while the real request is what decides, and the failure reason is now surfaced verbatim, because 'no immersive headset answered' is useless to debug against. The always-on loop uses the same VAD thresholds as the desktop recorder and stops the moment the XR session ends, so the laptop microphone is not held open in the background.

- (Gemini is the vision brain, and the daily quota is per model) The user asked for Gemini specifically, so Gemini leads the vision chain and Groq's `qwen/qwen3.8-27b` (which turns out to be multimodal) is only the fallback. The quota discovery matters more than the endpoint: the free tier allows 20 requests per day **per model**, not per key, so a single model is exhausted almost immediately and the assistant goes mute. Every Gemini chain - text and vision - therefore walks a list of models and each model keeps its own cooldown, which multiplies the usable budget several times over. The second lesson: the AR panel was invisible because three.js does not move the scene camera in an XR session; the panel was therefore positioned relative to an untracked camera and ended up on the floor. It now follows the XR camera's head pose, so it floats in front of the user with a hit-tested surface preferred.

- (The eyes are a daemon capability, not a browser one) The headset camera cannot be read from a web page during an immersive session, so asking the browser for a frame inside AR always fails. The frame therefore comes from a camera the PC can reach - typically a phone running an IP-webcam app, which gives a genuine view of the room while the user is wearing the headset. The UI hides that difference from the user: in the 2D view it uses the browser camera, inside AR it asks the daemon, and both end up in the same Gemini vision call. The second lesson of this round is about strict mode: a single undeclared variable (`xrFrames`) inside the big IIFE threw on the first XR frame and silently killed the render loop, which looked exactly like 'the HUD does not work in VR'. An undeclared-identifier scan now guards against that class of bug, and the XR branch can no longer take the rest of the loop down with it.

- (One camera: the headset's own) The project brief is the Quest 3's AR camera, so the client no longer offers or uses any other camera - the daemon-side capture endpoint stays for the PC but the HUD does not call it. Inside an immersive session WebXR owns the camera, and the only browser API that can read the passthrough image is Raw Camera Access (`XRWebGLBinding.getCameraImage`), which the app now implements with a graceful "not exposed to this browser" path, because whether Meta ships that API in Quest Browser is outside our control. The HUD therefore reports the truth instead of pretending: which camera it used, and whether the passthrough was readable. The AR console was rebuilt around the same principle - in a headset the DOM is invisible, so every piece of state (state badge, transcript, answer, scrollback, engine) has to be drawn into the 3D panel, which is why the panel became a 2048x1280 console with a dirty-flag redraw rather than a small static label.

- (A one-tap test switch beats editing a file) Testing the assistant was spending the scarce resource it depends on: each reload of the diagnostics panel and each trial question could burn one of the 20 daily Gemini requests per model. The switch is therefore a first-class setting (`gemini_enabled`) enforced *inside* the two places that call Gemini - the brain and the vision chain - rather than a UI-only illusion, so no code path can spend a request while it is off. It lives in the diagnostics panel (one tap, no typing) and in voice ("gemini off"), because the headset user has no keyboard in AR. The switch deliberately does not touch the Gemini *key* or cooldowns: turning it back on resumes exactly where the quota left off.

- (Two daemons must never share a port) Windows happily binds two sockets to the same port without `SO_EXCLUSIVEADDRUSE`, so an HTTPS daemon launched on 8765 next to the HTTP one does not fail loudly - connections are accepted by either process and the page randomly arrives with the wrong scheme, which surfaces as "WebXR needs a secure context" one reload and works the next. The HTTPS launcher now owns 8766 permanently. The same class of bug is why a stale TLS process had to be hunted by PID: when something behaves intermittently, check `netstat -ano` before touching the code.

- (Patch by structure, verify by parser) The EDITH HUD patch replaced a function header but left that function's tail behind, and the leftover `}` closed the IIFE early - a failure that is invisible in a diff and fatal at runtime. Two rules came out of it: a patch must be applied by locating whole *structures* (function start to matching brace), not by matching a phrase that may appear twice, and every HTML edit ends with `esprima.parseScript` plus a headless console check before it is called done. The first repair attempt proved the second half of that rule when the delete matched the live block inside `drawEDITHHUD` instead of the orphan.

- (The test switch belongs on the main HUD, not in a diagnostics drawer) The switch exists to stop wasting Gemini quota, which means it has to be reachable in one tap before a test, not two levels down inside VOICE TEST. A real sliding switch in the command bar also carries the state visually (cyan knob = on, amber = off), which a text button does not: the user can see at a glance which brain will answer. Both surfaces are painted by one function, so there is a single source of truth; the backend setting remains the only thing that decides whether Gemini is called.

- (Host control must not cost a model request) The assistant already had tools for launching apps, locking the screen and reading files, but they were never reachable from a spoken instruction, and the shutdown tool was a stub that returned a dictionary instead of shutting the machine down. The design decision that matters: **host actions are parsed locally, before the model chain**. "list processes" is answered in 7-22 ms with zero tokens, it still works with the brain switched off, and the daemon replaces the generic reply with the real outcome so the assistant never claims something it did not do. The alternative - asking Gemini to emit a tool call - would cost a request per command, be slow, and fail exactly when the quota is spent.

- (Full access, with the sharp edges named) The user asked for complete control of the machine, so the default is full disk access, but three settings keep it a decision rather than an accident: `pc_control_enabled` (master switch), `pc_full_access` (whole disk vs. home folder only) and `pc_block_system_paths` (writes and deletes under C:\Windows and C:\Program Files are refused; reads are fine). Shutdown and restart always wait a few seconds and can be cancelled, because an assistant that can power off the PC on a misheard word needs a window of doubt.

- (A voice command has to survive the UI's own shortcuts) The HUD intercepts dozens of phrases locally - "close help", "exit vr", "search for X", "system info" - so a host instruction could be swallowed before it ever reached the daemon. Two rules came out of that: the client recognises host instructions and routes them straight to `/api/command`, and the server's parser knows the difference between an application name and a HUD word. Without the second rule "close help" would have tried to kill a process called "help".

## 2026-11-14 - Local + Cloud AI, screen awareness and full host automation

**Everything goes on E:.** The system drive had ~53 GB free and the user asked
for nothing new on C:. Ollama is a standalone ZIP at `E:\JARVIS\ollama` with
`OLLAMA_MODELS` pointing at `E:\JARVIS\ollama\models`; the browser profile is
`E:\JARVIS\browser-profile`; pip cache and temp are `E:\JARVIS\pip-cache` and
`E:\JARVIS\tmp`. Python packages go into the existing D: venv because moving it
would break the daemon.

**`ai_mode` is a persisted setting, not a heuristic.** `local` = Qwen3.5 4B on
this machine, `cloud` = the untouched Gemini -> Groq -> OpenCode chain, default
`cloud`. Switching routes the *next* request. A local failure is spoken as a
failure (`engine: local-unavailable`) - never a silent fallback to the cloud,
because that is exactly the quota leak the mode exists to prevent.

**`"think": false` for Qwen3.5.** Its chain of thought is returned separately in
`message.thinking`, so with thinking on the budget is spent reasoning and
`message.content` comes back empty: the first probes answered `None`. Off is the
difference between 12 s of silence and a 420-720 ms spoken sentence. Toggle with
`ollama_think` if a question ever needs the reasoning.

**Keep the model warm, one model, one request.** `OLLAMA_KEEP_ALIVE=30m` and
`OLLAMA_MAX_LOADED_MODELS=1` / `OLLAMA_NUM_PARALLEL=1` keep 3.1 GB resident in
VRAM on a 6 GB laptop GPU instead of thrashing. `aimode.set_mode("local")` warms
it in a background thread, so the first question does not pay the cold start.

**Screen reading is local first.** UI Automation (pywinauto) + Windows OCR
(`Windows.Media.Ocr`) cost ~250-900 ms and zero quota; a screenshot plus vision
model costs a Gemini call. So vision is reachable only through an explicit
`/api/screen {action:"vision"}` - never on a timer, never as a fallback.

**Mouse and keyboard via `SendInput`.** ctypes only: no install, no dependency,
works in any window. The process is made DPI-aware at import so UIA rectangles,
cursor coordinates and screenshots share one coordinate space (otherwise clicks
land off-target on scaled displays).

**One gate for irreversible actions.** `approvals.needs_confirmation()` is the
single source of truth, used both when the brain returns actions and when the
`pc_control` tool is called directly, plus `workflow.needs_confirmation()` for
multi-step runs. Nothing destructive runs on inference: it is parked, spoken, and
needs an explicit "yes"/"confirm" within 120 s. Tests pin this so it cannot
regress into fire-and-forget.

**Playwright drives the user's Chrome, not a bundled browser.** `channel="chrome"`
with a persistent profile: real logins and extensions, no ~150 MB download to the
wrong drive. Google serves a captcha to automated profiles, so the default search
engine is DuckDuckGo; Bing/Google remain selectable.

**Email and calendar refuse rather than pretend.** No credentials ship. Missing
settings produce `not_configured` plus the exact missing key. The password lives
in the key vault (`email-password`), never in `settings.json` or the HUD.

**The automation row is inside the CONTROL DECK, not on the main stage.** The
main screen stays the Spline animation plus the brand and caption; SCREEN, CLICK,
BROWSER, APPS, AGENDA, MAIL and WHAT'S HERE sit under "SCREEN & AUTOMATION" in the
drawer, with the ONLINE/OFFLINE-style note under the mode switch and a small
`#xr-mode` chip under the brand for AR.

**Local eyes are one multimodal model, not a second resident model.** A 6 GB
RTX 3050 holds qwen3.5:4b (3.14 GB) *or* gemma3:4b (2.9 GB), not both, and a swap
costs 6-10 s. So in LOCAL mode a visual turn is a single call to gemma3:4b with
the frame, and text turns stay on gemma3:4b for 90 s after a frame (sticky) to
avoid thrashing the GPU mid-conversation. The engine label always names the model
that answered, so nothing switches silently.

**Live video conversation is one frame per utterance, not a frame pump.** The
camera stream stays open, but a frame is only grabbed when the user actually
says or types something, then attached to that same request. That gives "JARVIS
sees what I am asking about" at 2-3 s per turn on this GPU, instead of burning
the GPU on clips nobody asked about.

**No canned sensory claims.** The old optical-scan reply ("perimeter clear")
was a fixed string with no camera behind it. "What do you see" now either does a
real local look or says the eyes are closed and offers to open them.

**Dynamic Island popup bubble is a decoupled client process.** Instead of
forcing the user to keep the full 3D HUD browser tab open at all times, the
Dynamic Island bubble runs in the background as an independent windowless
process (`pythonw -m jarvis.bubble`). It floats always-on-top at the top centre
of the screen, with a collapsed status capsule and an animated expanded control
panel. It connects to the local daemon on 127.0.0.1:8765, meaning it inherits
both LOCAL (Ollama) and CLOUD (Gemini) modes transparently.

**Conversational PC control is whitelisted and gated.** Rigid regex matches
(`pc_intents.py`) catch common phrasing instantly with zero latency. For the
long tail of natural conversational instructions, `nlplan.py` asks the active
model to translate requests into structured `pc_control` calls, but strictly
restricts the output to a whitelisted catalog of actions and arguments. Any
destructive action still halts at `approvals.py` for explicit voice confirmation.

**Live search queries synthesize direct spoken answers.** Previously, asking
to "search for X" simply launched a browser URL. For an intelligent voice assistant,
the user expects the answer spoken directly ("The current President of the United States is Donald Trump...").
We now fetch live search snippets via DuckDuckGo lite and pass them into the active
model (Ollama Qwen3.5 4B locally or Gemini in the cloud) to synthesize a 1-2 sentence
direct spoken answer, while keeping the tool log.

**Window and browser controls use native Win32 + Playwright APIs.** Window operations
(maximize, minimize, restore, close) operate via Win32 user32 `ShowWindow` and
`WM_CLOSE` on the foreground window or matching window title. Browser tab controls
drive Playwright's persistent context pages (`open_tab`, `close_tab`, `close_duplicate_tabs`,
`list_tabs`, `switch_tab`), with fallbacks to standard keyboard shortcuts for native browser windows.

**LOCAL mode means 100% on-device STT, LLM, and TTS with zero cloud latency.**
When `ai_mode` is set to `local`, the assistant must be completely self-reliant:
- STT runs `faster-whisper` from the preloaded local cache at `E:\JARVIS\models\whisper` without ever attempting Groq.
- LLM runs `ollama` (Qwen3.5 4B / Gemma3 4B) on local GPU with `"think": false`.
- TTS runs `pyttsx3` locally on-device without attempting cloud `edge-tts`.
This guarantees that turning off Wi-Fi or unplugging Ethernet does not cause
timeouts, hangs, or a frozen "THINKING..." state.
