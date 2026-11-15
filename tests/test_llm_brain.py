"""Tests for the hosted brain helpers (jarvis.llm and the brain fallback chain)."""
import json
import urllib.error

from jarvis import brain, llm


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload.encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _http_error(code):
    def raiser(*args, **kwargs):
        raise urllib.error.HTTPError("https://groq", code, "err", {}, None)

    return raiser


def test_groq_key_reads_vault(monkeypatch):
    monkeypatch.setattr(llm, "groq_key", lambda: "gsk-test")
    assert llm.chat_available() is True


def test_chat_groq_returns_answer(monkeypatch):
    captured = {}

    def fake_post(key, model, messages, temperature, max_tokens, timeout):
        captured["model"] = model
        captured["messages"] = messages
        return "Paris, sir."

    monkeypatch.setattr(llm, "groq_key", lambda: "gsk-test")
    monkeypatch.setattr(llm, "_post_chat", fake_post)
    answer = llm.chat_groq("Capital of France?", system="be brief")
    assert answer == "Paris, sir."
    assert captured["model"] == llm.DEFAULT_GROQ_CHAT_MODEL
    assert captured["messages"][0]["role"] == "system"


def test_chat_groq_without_key(monkeypatch):
    monkeypatch.setattr(llm, "groq_key", lambda: None)
    assert llm.chat_groq("hello") is None


def test_chat_groq_falls_back_to_next_model(monkeypatch):
    seen = []

    def fake_post(key, model, messages, temperature, max_tokens, timeout):
        seen.append(model)
        if model == llm.DEFAULT_GROQ_CHAT_MODEL:
            raise urllib.error.HTTPError("https://groq", 404, "no model", {}, None)
        return "Tokyo, sir."

    monkeypatch.setattr(llm, "groq_key", lambda: "gsk-test")
    monkeypatch.setattr(llm, "_post_chat", fake_post)
    answer = llm.chat_groq("Capital of Japan?")
    assert answer == "Tokyo, sir."
    assert len(seen) == 2


def test_brain_uses_groq_when_gemini_is_unavailable(monkeypatch):
    monkeypatch.setattr(brain, "_gemini_direct_respond", lambda text, context=None: None)
    monkeypatch.setattr(brain, "_groq_respond", lambda text, context=None: brain.Reply(speech="Fast answer, sir."))
    reply = brain.respond("What is the capital of France?")
    assert reply.speech == "Fast answer, sir."


def test_brain_groq_reply_strips_markdown(monkeypatch):
    monkeypatch.setattr(llm, "chat_available", lambda: True)
    monkeypatch.setattr(
        llm,
        "chat_groq",
        lambda prompt, system=None, max_tokens=90, **kwargs: "*Paris* - the city of light.",
    )
    reply = brain._groq_respond("Where is Paris?")
    assert reply is not None
    assert "*" not in reply.speech
    assert "Paris" in reply.speech


def test_detect_opencode_cli_env_override(monkeypatch, tmp_path):
    fake = tmp_path / "opencode-cli.exe"
    fake.write_bytes(b"MZ")
    monkeypatch.setenv("JARVIS_OPENCODE_CLI", str(fake))
    assert brain._detect_opencode_cli() == str(fake)


def test_detect_opencode_cli_returns_none_without_candidates(monkeypatch):
    monkeypatch.delenv("JARVIS_OPENCODE_CLI", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", "")
    monkeypatch.setenv("PROGRAMFILES", "")
    assert brain._detect_opencode_cli() is None
