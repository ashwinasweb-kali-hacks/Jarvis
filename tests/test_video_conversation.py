"""Tests for the local eyes and the live video conversation path.

A 6 GB card holds one 4B model, so a visual turn is answered by the multimodal
model in a single call (frame + question). These tests pin that behaviour and
make sure LOCAL mode never quietly borrows a cloud model for vision.
"""
import base64

import pytest

from jarvis import ollama_local, vision


PNG = b"\x89PNG\r\n\x1a\n fake image bytes"


def _local_mode(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_AI_MODE", "local")


def test_vision_model_is_configurable(monkeypatch):
    monkeypatch.delenv("JARVIS_OLLAMA_VISION_MODEL", raising=False)
    assert ollama_local.vision_model_name() == "gemma3:4b"
    monkeypatch.setenv("JARVIS_OLLAMA_VISION_MODEL", "qwen3-vl:2b")
    assert ollama_local.vision_model_name() == "qwen3-vl:2b"


def test_a_frame_makes_ollama_use_the_vision_model(monkeypatch):
    seen = {}

    def fake_request(path, payload=None, timeout=10.0):
        seen["payload"] = payload
        return {"message": {"content": "A desk with a laptop."}, "done": True}

    monkeypatch.setattr(ollama_local, "_request", fake_request)
    answer = ollama_local.chat("what is this", images=[base64.b64encode(PNG).decode()])
    assert answer == "A desk with a laptop."
    assert seen["payload"]["model"] == ollama_local.vision_model_name()
    message = seen["payload"]["messages"][-1]
    assert message["images"] == [base64.b64encode(PNG).decode()]
    assert seen["payload"]["messages"][0]["content"] == ollama_local.VISION_SYSTEM_PROMPT


def test_text_turn_after_a_frame_stays_on_one_model(monkeypatch):
    """No 6-10 s model swap between a look and the next spoken question."""
    monkeypatch.setattr(ollama_local, "_last_vision_at", 0.0)
    monkeypatch.setattr(ollama_local, "_request",
                        lambda path, payload=None, timeout=10.0: {"message": {"content": "ok"}})
    ollama_local.chat("look", images=[base64.b64encode(PNG).decode()])
    seen = {}

    def capture(path, payload=None, timeout=10.0):
        seen.update(payload)
        return {"message": {"content": "yes"}}

    monkeypatch.setattr(ollama_local, "_request", capture)
    ollama_local.chat("and now a plain question")
    assert seen["model"] == ollama_local.vision_model_name()
    assert "images" not in seen["messages"][-1]


def test_plain_text_turn_uses_the_text_model(monkeypatch):
    monkeypatch.setattr(ollama_local, "_last_vision_at", 0.0)
    monkeypatch.setattr(ollama_local, "list_loaded", lambda timeout=1.5: [])
    seen = {}

    def capture(path, payload=None, timeout=10.0):
        seen.update(payload)
        return {"message": {"content": "Rome, sir."}}

    monkeypatch.setattr(ollama_local, "_request", capture)
    ollama_local.chat("capital of Italy?")
    assert seen["model"] == ollama_local.model_name()


def test_text_turn_prefers_whichever_model_is_resident(monkeypatch):
    """Never pay a 6-10 s swap when the resident model can answer."""
    monkeypatch.setattr(ollama_local, "_last_vision_at", 0.0)
    monkeypatch.setattr(ollama_local, "list_loaded",
                        lambda timeout=1.5: [{"name": ollama_local.vision_model_name()}])
    assert ollama_local.preferred_model() == ollama_local.vision_model_name()

    monkeypatch.setattr(ollama_local, "list_loaded",
                        lambda timeout=1.5: [{"name": ollama_local.model_name()}])
    assert ollama_local.preferred_model() == ollama_local.model_name()


def test_local_mode_vision_never_calls_a_cloud_model(monkeypatch):
    _local_mode(monkeypatch)
    monkeypatch.setattr(vision, "_ollama_describe",
                        lambda image, prompt, timeout: ("A white wall.", "local:gemma3:4b"))

    def cloud(*args, **kwargs):
        raise AssertionError("a cloud vision model was contacted in LOCAL mode")

    monkeypatch.setattr(vision, "_gemini_describe", cloud)
    monkeypatch.setattr(vision, "_groq_describe", cloud)

    result = vision.describe_image(PNG)
    assert result["ok"] is True
    assert result["engine"] == "local:gemma3:4b"
    assert result["mode"] == "local"


def test_local_mode_vision_failure_is_reported_not_delegated(monkeypatch):
    _local_mode(monkeypatch)

    def boom(image, prompt, timeout):
        raise RuntimeError("Ollama is not running")

    monkeypatch.setattr(vision, "_ollama_describe", boom)
    monkeypatch.setattr(vision, "_gemini_describe",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no cloud in local mode")))
    result = vision.describe_image(PNG)
    assert result["ok"] is False
    assert "Ollama is not running" in result["error"]


def test_cloud_mode_still_prefers_gemini(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_AI_MODE", "cloud")
    monkeypatch.setattr(vision, "_gemini_describe",
                        lambda url, prompt, timeout: ("A blue sky.", "gemini:gemini-3.5-flash"))
    monkeypatch.setattr(vision, "_ollama_describe",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("local eyes in cloud mode")))
    result = vision.describe_image(PNG)
    assert result["ok"] is True
    assert result["engine"] == "gemini:gemini-3.5-flash"
    assert result["mode"] == "cloud"


def test_brain_routes_a_frame_to_the_local_eyes(monkeypatch):
    _local_mode(monkeypatch)
    from jarvis import brain

    seen = {}

    def fake_chat(text, **kwargs):
        seen.update(kwargs)
        seen["text"] = text
        return "A monitor showing code, sir."

    monkeypatch.setattr(ollama_local, "chat", fake_chat)
    reply = brain.respond("what do you see", image=PNG)
    assert reply.speech == "A monitor showing code, sir."
    assert reply.engine.startswith("local:")
    assert seen["images"] == [base64.b64encode(PNG).decode()]
    assert seen["system"] == ollama_local.VISION_SYSTEM_PROMPT


def test_brain_local_vision_failure_does_not_fall_back_to_cloud(monkeypatch):
    _local_mode(monkeypatch)
    from jarvis import brain

    monkeypatch.setattr(ollama_local, "chat", lambda text, **kwargs: None)
    monkeypatch.setattr(ollama_local, "status",
                        lambda refresh=False: {"available": True, "model_present": True,
                                               "model": "qwen3.5:4b", "vision_present": True,
                                               "vision_model": "gemma3:4b"})
    monkeypatch.setattr(ollama_local, "last_error", lambda: "camera frame too large")

    def cloud(*args, **kwargs):
        raise AssertionError("cloud brain used in LOCAL mode")

    monkeypatch.setattr(brain, "_oauth_respond", cloud)
    reply = brain.respond("what do you see", image=PNG)
    assert reply.engine == "local-unavailable"
    assert "will not switch to the cloud" in reply.speech


def test_cloud_brain_answers_a_frame_with_the_vision_chain(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_AI_MODE", "cloud")
    from jarvis import brain

    monkeypatch.setattr(vision, "describe_image",
                        lambda image, prompt=None: {"ok": True, "description": "A red mug.",
                                                    "engine": "gemini:gemini-3.5-flash"})
    reply = brain.respond("what is this", image=PNG)
    assert reply.speech == "A red mug."
    assert reply.engine == "gemini:gemini-3.5-flash"
