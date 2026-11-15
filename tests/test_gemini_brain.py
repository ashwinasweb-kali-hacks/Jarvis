"""Tests for the Gemini brain backend (jarvis.gemini)."""
import time
import urllib.error

import pytest

from jarvis import brain, gemini


@pytest.fixture(autouse=True)
def _no_cooldowns(monkeypatch):
    """The cooldowns are persisted on disk; tests must not inherit them."""
    monkeypatch.setattr(gemini, "_MODEL_COOLDOWN", {})


def test_gemini_key_prefers_environment(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert gemini.gemini_key() == "from-env"


def test_gemini_key_falls_back_to_vault(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(gemini, "gemini_key", lambda: "from-vault")
    assert gemini.chat_available() is True


def test_chat_gemini_sends_reasoning_effort_none(monkeypatch):
    captured = {}

    def fake_post(key, model, messages, temperature, max_tokens, timeout, fast):
        captured["fast"] = fast
        captured["model"] = model
        captured["messages"] = messages
        return "Paris, sir."

    monkeypatch.setattr(gemini, "gemini_key", lambda: "key")
    monkeypatch.setattr(gemini, "_post_chat", fake_post)
    answer = gemini.chat_gemini("Capital of France?", system="be brief")
    assert answer == "Paris, sir."
    assert captured["fast"] is True
    assert captured["model"] == gemini.DEFAULT_GEMINI_MODEL
    assert captured["messages"][0]["role"] == "system"


def test_chat_gemini_retries_without_fast_flag(monkeypatch):
    calls = []

    def fake_post(key, model, messages, temperature, max_tokens, timeout, fast):
        calls.append(fast)
        if fast:
            raise urllib.error.HTTPError("https://gemini", 400, "bad request", {}, None)
        return "Paris, sir."

    monkeypatch.setattr(gemini, "gemini_key", lambda: "key")
    monkeypatch.setattr(gemini, "_post_chat", fake_post)
    answer = gemini.chat_gemini("Capital of France?")
    assert answer == "Paris, sir."
    assert calls == [True, False]


def test_chat_gemini_next_model_on_404(monkeypatch):
    seen = []

    def fake_post(key, model, messages, temperature, max_tokens, timeout, fast):
        seen.append(model)
        if model == gemini.DEFAULT_GEMINI_MODEL:
            raise urllib.error.HTTPError("https://gemini", 404, "not found", {}, None)
        return "Tokyo, sir."

    monkeypatch.setattr(gemini, "gemini_key", lambda: "key")
    monkeypatch.setattr(gemini, "_post_chat", fake_post)
    answer = gemini.chat_gemini("Capital of Japan?")
    assert answer == "Tokyo, sir."
    assert len(seen) == 2


def test_chat_gemini_without_key(monkeypatch):
    monkeypatch.setattr(gemini, "gemini_key", lambda: None)
    assert gemini.chat_gemini("hello") is None


def test_brain_prefers_gemini_over_groq(monkeypatch):
    order = []

    def fake_gemini(text, context=None):
        order.append("gemini")
        return brain.Reply(speech="Gemini answer, sir.")

    def fake_groq(text, context=None):
        order.append("groq")
        return brain.Reply(speech="Groq answer, sir.")

    monkeypatch.setattr(brain, "_gemini_direct_respond", fake_gemini)
    monkeypatch.setattr(brain, "_groq_respond", fake_groq)
    reply = brain.respond("What is the capital of France?")
    assert reply.speech == "Gemini answer, sir."
    assert order == ["gemini"]


def test_brain_falls_back_to_groq(monkeypatch):
    monkeypatch.setattr(brain, "_gemini_direct_respond", lambda text, context=None: None)
    monkeypatch.setattr(
        brain,
        "_groq_respond",
        lambda text, context=None: brain.Reply(speech="Groq answer, sir."),
    )
    reply = brain.respond("What is the capital of France?")
    assert reply.speech == "Groq answer, sir."


def test_brain_gemini_reply_strips_markdown(monkeypatch):
    monkeypatch.setattr(gemini, "chat_available", lambda: True)
    monkeypatch.setattr(
        gemini,
        "chat_gemini",
        lambda prompt, system=None, max_tokens=256, **kwargs: "*Paris* - the city of light.",
    )
    reply = brain._gemini_direct_respond("Where is Paris?")
    assert reply is not None
    assert "*" not in reply.speech
    assert "Paris" in reply.speech


def test_parse_retry_hint():
    assert gemini._parse_retry_hint("Please retry in 23h13m55s") == 23 * 3600 + 13 * 60
    assert gemini._parse_retry_hint('"retryDelay": "83635s"') == 83635.0
    assert gemini._parse_retry_hint("no hint here") is None


def test_chat_gemini_429_moves_to_next_model(monkeypatch):
    seen = []

    def fake_post(key, model, messages, temperature, max_tokens, timeout, fast):
        seen.append(model)
        if model == gemini.DEFAULT_GEMINI_MODEL:
            raise urllib.error.HTTPError("https://gemini", 429, "quota", {}, None)
        return "Fallback answer, sir."

    monkeypatch.setattr(gemini, "gemini_key", lambda: "key")
    monkeypatch.setattr(gemini, "_post_chat", fake_post)
    monkeypatch.setattr(gemini, "_MODEL_COOLDOWN", {})
    answer = gemini.chat_gemini("Anything?")
    assert answer == "Fallback answer, sir."
    assert seen[0] == gemini.DEFAULT_GEMINI_MODEL
    assert seen[1] == gemini.GEMINI_MODEL_CHAIN[1]


def test_chat_gemini_skips_cooled_down_model(monkeypatch):
    seen = []
    monkeypatch.setattr(gemini, "gemini_key", lambda: "key")
    monkeypatch.setattr(gemini, "_MODEL_COOLDOWN", {gemini.DEFAULT_GEMINI_MODEL: time.time() + 600})

    def fake_post(key, model, messages, temperature, max_tokens, timeout, fast):
        seen.append(model)
        return "Second model, sir."

    monkeypatch.setattr(gemini, "_post_chat", fake_post)
    answer = gemini.chat_gemini("Anything?")
    assert answer == "Second model, sir."
    assert gemini.DEFAULT_GEMINI_MODEL not in seen


def test_cooldowns_reports_remaining_seconds(monkeypatch):
    monkeypatch.setattr(gemini, "_MODEL_COOLDOWN", {"gemini-3.5-flash": time.time() + 120})
    remaining = gemini.cooldowns()
    assert "gemini-3.5-flash" in remaining
    assert 0 < remaining["gemini-3.5-flash"] <= 120
