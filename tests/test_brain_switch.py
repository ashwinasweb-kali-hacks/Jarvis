"""Tests for the master brain switch (`brain_enabled`).

With the master switch off the daemon must not contact ANY model - hosted or
local - so a testing session cannot spend a credit. The reply the user sees is
built inside ``respond()`` and never leaves the process.
"""
from __future__ import annotations

import pytest

from jarvis import brain, vision

BACKENDS = (
    "_oauth_respond",
    "_gemini_direct_respond",
    "_groq_respond",
    "_openjarvis_respond",
    "_gpt4all_respond",
    "_local_uncensored_respond",
    "_stub_respond",
)


def _trap(calls, name):
    def _fn(*_a, **_k):
        calls.append(name)
        raise AssertionError("backend {0} must not run while the brain is off".format(name))

    return _fn


def test_master_switch_blocks_every_backend(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_BRAIN_ENABLED", "0")
    calls = []
    for name in BACKENDS:
        monkeypatch.setattr(brain, name, _trap(calls, name))

    reply = brain.respond("What is the capital of France?")

    assert calls == []
    assert reply.engine == "brain-off"
    assert "switched off" in reply.speech.lower()
    assert reply.actions == []


def test_master_switch_on_still_answers(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_BRAIN_ENABLED", "1")
    monkeypatch.setattr(
        brain, "_oauth_respond",
        lambda *a, **k: brain.Reply(speech="Paris, sir.", engine="test"),
    )

    reply = brain.respond("What is the capital of France?")
    assert reply.speech == "Paris, sir."
    assert reply.engine == "test"


@pytest.mark.parametrize("value", ["0", "false", "off", "no"])
def test_master_switch_off_spellings(monkeypatch, value):
    monkeypatch.setenv("JARVIS_SETTING_BRAIN_ENABLED", value)
    assert brain.respond("hello").engine == "brain-off"


def test_vision_respects_master_switch(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_BRAIN_ENABLED", "0")

    calls = []

    def _trap_vision(name):
        def _fn(*_a, **_k):
            calls.append(name)
            raise AssertionError(name + " must not run while the brain is off")

        return _fn

    monkeypatch.setattr(vision, "_gemini_describe", _trap_vision("gemini"))
    monkeypatch.setattr(vision, "_groq_describe", _trap_vision("groq"))

    result = vision.describe_image(b"\xff\xd8\xff\xd9")
    assert result["ok"] is False
    assert "switched off" in result["error"]
    assert calls == []
