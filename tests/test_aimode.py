"""Tests for the Local / Cloud brain switch and the local provider surface."""
from __future__ import annotations

import pytest

from jarvis import aimode, brain, ollama_local, pc_intents


@pytest.fixture(autouse=True)
def cloud_mode(monkeypatch):
    """Each test starts from the shipped default and never writes the real store."""
    monkeypatch.setenv("JARVIS_SETTING_AI_MODE", "cloud")
    yield


def test_default_mode_is_cloud(monkeypatch):
    monkeypatch.delenv("JARVIS_SETTING_AI_MODE", raising=False)
    monkeypatch.setattr(aimode.settings, "get", lambda key, default=None: "cloud" if key == "ai_mode" else default)
    assert aimode.mode() == "cloud"
    assert aimode.is_local() is False


def test_unknown_mode_falls_back_to_cloud(monkeypatch):
    monkeypatch.setattr(aimode.settings, "get", lambda key, default=None: "banana" if key == "ai_mode" else default)
    assert aimode.mode() == "cloud"


@pytest.mark.parametrize("value,expected", [
    ("local", "local"), ("LOCAL", "local"), ("offline", "local"), ("ollama", "local"),
    ("cloud", "cloud"), ("gemini", "cloud"), ("online", "cloud"),
])
def test_set_mode_accepts_aliases(monkeypatch, value, expected):
    written = {}
    monkeypatch.setattr(aimode.settings, "set", lambda key, val: written.update({key: val}) or {"ok": True})
    monkeypatch.setattr(aimode, "status", lambda: {"mode": expected})
    monkeypatch.setattr(aimode.ollama_local, "ensure_warm", lambda background=True: {"ok": True})
    out = aimode.set_mode(value)
    assert out["ok"] is True
    assert out["mode"] == expected
    assert written.get("ai_mode") == expected


def test_set_mode_refuses_nonsense(monkeypatch):
    out = aimode.set_mode("quantum")
    assert out["ok"] is False
    assert "local" in out["error"]


def test_local_mode_never_calls_the_cloud(monkeypatch):
    """A local failure must be spoken as a failure, not papered over by Gemini."""
    monkeypatch.setenv("JARVIS_SETTING_AI_MODE", "local")
    called = {"gemini": 0, "groq": 0, "ollama": 0}

    monkeypatch.setattr(brain, "_gemini_direct_respond", lambda *a, **k: called.__setitem__("gemini", called["gemini"] + 1) or None)
    monkeypatch.setattr(brain, "_groq_respond", lambda *a, **k: called.__setitem__("groq", called["groq"] + 1) or None)
    monkeypatch.setattr(brain, "_ollama_respond", lambda *a, **k: called.__setitem__("ollama", called["ollama"] + 1) or None)
    monkeypatch.setattr(ollama_local, "status", lambda refresh=False: {
        "available": False, "model": "qwen3.5:4b", "model_present": False, "error": "Ollama is not running.",
    })

    reply = brain.respond("what is the capital of France")
    assert called["ollama"] == 1
    assert called["gemini"] == 0
    assert called["groq"] == 0
    assert reply.engine == "local-unavailable"
    assert "will not switch" in reply.speech.lower()


def test_local_mode_reply_names_the_local_engine(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_AI_MODE", "local")
    monkeypatch.setattr(brain, "_ollama_respond", lambda *a, **k: brain.Reply(
        speech="Paris, sir.", engine="local:qwen3.5:4b"))
    monkeypatch.setattr(brain, "_gemini_direct_respond", lambda *a, **k: pytest.fail("cloud called in local mode"))
    reply = brain.respond("what is the capital of France")
    assert reply.engine == "local:qwen3.5:4b"
    assert reply.speech == "Paris, sir."


def test_mode_voice_switch_is_zero_token(monkeypatch):
    written = {}
    monkeypatch.setattr(aimode.settings, "set", lambda key, val: written.update({key: val}) or {"ok": True})
    monkeypatch.setattr(aimode, "status", lambda: {
        "mode": "local", "ready": True, "reason": "Local model ready (GPU)",
        "local": {"model": "qwen3.5:4b", "gpu": True, "model_present": True},
        "cloud": {"gemini": True, "groq": True},
    })
    monkeypatch.setattr(aimode.ollama_local, "ensure_warm", lambda background=True: {"ok": True})
    monkeypatch.setattr(brain, "_detect_pc_actions", lambda text: pytest.fail("mode switch hit host control"))

    reply = brain.respond("switch to local mode")
    assert reply.engine == "ai-mode"
    assert reply.tokens_used == 0
    assert written.get("ai_mode") == "local"
    assert "local" in reply.speech.lower()


@pytest.mark.parametrize("phrase", [
    "are you local", "is this local or cloud", "which mode are you running",
    "which model are you using", "ai mode", "brain status", "am i on cloud",
])
def test_mode_status_questions_are_local(monkeypatch, phrase):
    monkeypatch.setattr(aimode, "status", lambda: {
        "mode": "cloud", "ready": True, "reason": "Cloud model ready",
        "local": {"model": "qwen3.5:4b", "gpu": True, "model_present": True},
        "cloud": {"gemini": True, "groq": True},
    })
    monkeypatch.setattr(brain, "_detect_pc_actions", lambda text: [])
    monkeypatch.setattr(brain, "_gemini_direct_respond", lambda *a, **k: pytest.fail("status question hit the cloud"))
    reply = brain.respond(phrase)
    assert reply.engine == "ai-mode"
    assert "cloud" in reply.speech.lower()


def test_cloud_mode_does_not_touch_local_models(monkeypatch):
    """Cloud keeps the existing chain: local engines must stay out of it."""
    monkeypatch.setenv("JARVIS_SETTING_AI_MODE", "cloud")
    monkeypatch.setattr(brain, "OPENCODE_CLI_PATH", "")
    monkeypatch.setattr(brain, "_gemini_direct_respond", lambda *a, **k: None)
    monkeypatch.setattr(brain, "_groq_respond", lambda *a, **k: None)
    monkeypatch.setattr(brain, "_openjarvis_respond", lambda *a, **k: pytest.fail("local engine used in cloud mode"))
    monkeypatch.setattr(brain, "_gpt4all_respond", lambda *a, **k: pytest.fail("local engine used in cloud mode"))
    monkeypatch.setattr(brain, "_local_uncensored_respond", lambda *a, **k: pytest.fail("local engine used in cloud mode"))
    monkeypatch.setattr(brain, "_stub_respond", lambda text, ctx=None: brain.Reply(speech="stub", engine="stub"))
    reply = brain._oauth_respond("tell me something about the sea")
    assert reply is not None and reply.engine == "stub"


# ------------------------------------------------------------------ ollama_local
def test_ollama_status_is_honest_when_server_is_down(monkeypatch):
    def boom(path, payload=None, timeout=10.0):
        raise OSError("connection refused")

    monkeypatch.setattr(ollama_local, "_request", boom)
    st = ollama_local.status(refresh=True)
    assert st["available"] is False
    assert "not running" in st["error"].lower() or "unreachable" in st["error"].lower()
    assert ollama_local.chat("hello") is None


def test_ollama_think_flag_defaults_to_off(monkeypatch):
    monkeypatch.delenv("JARVIS_SETTING_OLLAMA_THINK", raising=False)
    monkeypatch.setattr(ollama_local, "_setting", lambda key, default=None: default)
    assert ollama_local._think() is False


def test_ollama_chat_reads_message_content(monkeypatch):
    monkeypatch.setattr(ollama_local, "_request", lambda path, payload=None, timeout=10.0: {
        "message": {"role": "assistant", "content": "  Paris, sir.  "},
        "done": True,
    })
    assert ollama_local.chat("capital of France?") == "Paris, sir."


def test_ollama_chat_ignores_hidden_thinking(monkeypatch):
    """Thinking-only replies have empty content: they are a failure, not an answer."""
    monkeypatch.setattr(ollama_local, "_request", lambda path, payload=None, timeout=10.0: {
        "message": {"role": "assistant", "content": "", "thinking": "Let me think about this..."},
        "done": True,
    })
    assert ollama_local.chat("hello") is None


def test_ollama_empty_reply_records_error(monkeypatch):
    def boom(path, payload=None, timeout=10.0):
        raise OSError("connection refused")

    monkeypatch.setattr(ollama_local, "_request", boom)
    assert ollama_local.chat("hello") is None
    assert ollama_local.last_error()


# ----------------------------------------------------------------- new intents
@pytest.mark.parametrize("phrase,action", [
    ("what is on my screen", "screen"),
    ("read my screen", "screen"),
    ("describe my screen", "screen"),
    ("click save", "screen_click"),
    ("press ctrl s", "press_key"),
    ("type hello world", "type_text"),
    ("scroll down 5", "scroll"),
    ("switch to notepad", "focus_window"),
    ("list windows", "list_windows"),
    ("install 7zip.7zip", "install_app"),
    ("uninstall spotify", "uninstall_app"),
    ("list installed apps", "list_installed"),
    ("run powershell Get-Date", "run_powershell"),
    ("what is on my calendar", "calendar"),
    ("read my email", "read_email"),
])
def test_new_intents(phrase, action):
    actions = pc_intents.detect(phrase)
    assert actions, phrase
    assert actions[0]["tool"] == "pc_control"
    assert actions[0]["args"]["action"] == action


def test_calendar_intent_is_not_an_app_launch():
    assert pc_intents.detect("what is on my calendar")[0]["args"]["action"] == "calendar"


def test_ui_switch_targets_are_not_windows():
    assert pc_intents.detect("switch to friday") == []
    assert pc_intents.detect("switch to local mode") == []


def test_spoken_intent_covers_screen_and_keys():
    assert "screen" in pc_intents.spoken_intent(pc_intents.detect("read my screen")).lower()
    assert "ctrl" in pc_intents.spoken_intent(pc_intents.detect("press ctrl s")).lower()
