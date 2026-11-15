"""Tests for the ``gemini_enabled`` test switch.

The switch exists so testing does not burn the Gemini free-tier quota: when it is
off, neither the brain nor the vision chain may touch Gemini.
"""
from __future__ import annotations

import pytest

from jarvis import brain, settings, vision


@pytest.mark.parametrize("value,expected", [
    ("0", False),
    ("false", False),
    ("FALSE", False),
    ("off", False),
    ("no", False),
    ("disabled", False),
    ("1", True),
    ("true", True),
    ("yes", True),
])
def test_flag_parses_env_strings(monkeypatch, value, expected):
    monkeypatch.setenv("JARVIS_SETTING_GEMINI_ENABLED", value)
    assert settings.flag("gemini_enabled", True) is expected


def test_flag_uses_default_when_unset(monkeypatch):
    monkeypatch.delenv("JARVIS_SETTING_GEMINI_ENABLED", raising=False)
    monkeypatch.setattr(settings, "get", lambda key, default=None: default)
    assert settings.flag("gemini_enabled", True) is True
    assert settings.flag("gemini_enabled", False) is False


def test_brain_skips_gemini_when_disabled(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_GEMINI_ENABLED", "0")

    from jarvis import gemini

    def _boom(*_a, **_k):  # pragma: no cover - must never run
        raise AssertionError("Gemini must not be called while disabled")

    monkeypatch.setattr(gemini, "chat_available", lambda: True)
    monkeypatch.setattr(gemini, "chat_gemini", _boom)

    assert brain._gemini_direct_respond("hello") is None


def test_vision_skips_gemini_when_disabled(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_GEMINI_ENABLED", "0")

    def _boom(*_a, **_k):  # pragma: no cover - must never run
        raise AssertionError("Gemini vision must not be called while disabled")

    monkeypatch.setattr(vision, "_gemini_describe", _boom)
    monkeypatch.setattr(vision, "_groq_describe", lambda *a, **k: ("a grey desk", "groq:test"))

    result = vision.describe_image(b"\xff\xd8\xff\xd9")
    assert result["ok"] is True
    assert result["engine"] == "groq:test"


def test_vision_uses_gemini_when_enabled(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_GEMINI_ENABLED", "1")

    monkeypatch.setattr(vision, "_gemini_describe", lambda *a, **k: ("a bright room", "gemini:test"))
    monkeypatch.setattr(vision, "_groq_describe", lambda *a, **k: (_ for _ in ()).throw(AssertionError("groq should not be reached")))

    result = vision.describe_image(b"\xff\xd8\xff\xd9")
    assert result["ok"] is True
    assert result["engine"] == "gemini:test"
