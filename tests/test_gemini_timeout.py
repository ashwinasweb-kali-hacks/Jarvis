"""A timeout in one Gemini model must not end the chain."""
import sys
import urllib.error

sys.path.insert(0, r"D:\downloads\jarvis-444-main")

from jarvis import gemini


def test_timeout_moves_to_the_next_model(monkeypatch):
    seen = []

    def fake_post(key, model, messages, temperature, max_tokens, timeout, fast):
        seen.append(model)
        if model == gemini.DEFAULT_GEMINI_MODEL:
            raise TimeoutError("timed out")
        return "Recovered answer, sir."

    monkeypatch.setattr(gemini, "gemini_key", lambda: "key")
    monkeypatch.setattr(gemini, "_post_chat", fake_post)
    monkeypatch.setattr(gemini, "_MODEL_COOLDOWN", {})

    answer = gemini.chat_gemini("Anything?")
    assert answer == "Recovered answer, sir."
    assert len(seen) >= 2


def test_http_error_still_moves_on(monkeypatch):
    seen = []

    def fake_post(key, model, messages, temperature, max_tokens, timeout, fast):
        seen.append(model)
        if model == gemini.DEFAULT_GEMINI_MODEL:
            raise urllib.error.HTTPError("https://g", 503, "busy", {}, None)
        return "Second model answer."

    monkeypatch.setattr(gemini, "gemini_key", lambda: "key")
    monkeypatch.setattr(gemini, "_post_chat", fake_post)
    monkeypatch.setattr(gemini, "_MODEL_COOLDOWN", {})

    answer = gemini.chat_gemini("Anything?")
    assert answer == "Second model answer."
    assert len(seen) >= 2
