"""Tests for the vision backend."""
import base64
import struct
import zlib

from jarvis import vision


def _png(width=64, height=64):
    raw = b""
    for y in range(height):
        raw += b"\x00"
        for x in range(width):
            raw += bytes((220, 40, 40) if 20 <= x < 44 and 20 <= y < 44 else (30, 60, 120))

    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_data_url_is_base64(monkeypatch):
    url = vision._as_data_url(b"abc", "image/png")
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == b"abc"


def test_describe_image_without_image():
    result = vision.describe_image(b"")
    assert result["ok"] is False
    assert "no image" in result["error"]


def test_describe_image_prefers_gemini(monkeypatch):
    monkeypatch.setattr(vision, "_gemini_describe",
                        lambda data_url, prompt, timeout: ("A red square on blue.", "gemini:gemini-3.5-flash-lite"))
    monkeypatch.setattr(vision, "_groq_describe",
                        lambda data_url, prompt, timeout: (_ for _ in ()).throw(RuntimeError("should not be used")))
    result = vision.describe_image(_png())
    assert result["ok"] is True
    assert result["description"] == "A red square on blue."
    assert result["engine"] == "gemini:gemini-3.5-flash-lite"


def test_describe_image_falls_back_to_groq(monkeypatch):
    def boom(data_url, prompt, timeout):
        raise RuntimeError("gemini quota")

    monkeypatch.setattr(vision, "_gemini_describe", boom)
    monkeypatch.setattr(vision, "_groq_describe",
                        lambda data_url, prompt, timeout: ("A dark room.", "groq:qwen/qwen3.8-27b"))
    result = vision.describe_image(_png())
    assert result["ok"] is True
    assert result["engine"] == "groq:qwen/qwen3.8-27b"
    assert any("gemini quota" in e for e in result["errors"])


def test_describe_image_reports_failure(monkeypatch):
    monkeypatch.setattr(vision, "_gemini_describe",
                        lambda data_url, prompt, timeout: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(vision, "_groq_describe",
                        lambda data_url, prompt, timeout: (None, None))
    result = vision.describe_image(_png())
    assert result["ok"] is False
    assert result["error"]


def test_gemini_vision_chain_stacks_models():
    """The daily quota is per model, so the chain must contain several."""
    assert len(vision.GEMINI_VISION_MODELS) >= 4
    assert vision.GEMINI_VISION_MODELS[0] == "gemini-3.5-flash"
