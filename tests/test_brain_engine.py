"""Tests for brain engine reporting (which backend answered) and the UI test hooks."""
from jarvis import brain
from jarvis.brain import Reply


def test_reply_to_dict_includes_engine():
    reply = Reply(speech="Hello, sir.", engine="gemini:gemini-3.5-flash")
    data = reply.to_dict()
    assert data["engine"] == "gemini:gemini-3.5-flash"
    assert data["speech"] == "Hello, sir."


def test_reply_engine_defaults_to_empty():
    assert Reply(speech="x").engine == ""


def test_respond_falls_back_to_offline_stub_engine(monkeypatch):
    monkeypatch.setattr(brain, "_gemini_direct_respond", lambda text, context=None: None)
    monkeypatch.setattr(brain, "_groq_respond", lambda text, context=None: None)
    monkeypatch.setattr(brain, "OPENCODE_CLI_PATH", "")
    monkeypatch.setattr(brain, "_local_uncensored_respond", lambda text, context=None: None)
    monkeypatch.setattr(brain, "_gpt4all_respond", lambda text, context=None: None)
    monkeypatch.setattr(brain, "_openjarvis_respond", lambda text, context=None: None)
    monkeypatch.setattr(brain, "_stub_respond", lambda text, context=None: Reply(speech="Standing by, sir."))

    reply = brain.respond("What is the meaning of life in the deep sea?")
    assert reply.engine == "offline-stub"


def test_gemini_backend_tags_its_engine(monkeypatch):
    from jarvis import gemini

    monkeypatch.setattr(gemini, "chat_available", lambda: True)
    monkeypatch.setattr(gemini, "last_model", lambda: "gemini-3.5-flash")
    monkeypatch.setattr(
        gemini,
        "chat_gemini",
        lambda prompt, system=None, max_tokens=256, **kwargs: "Paris, sir.",
    )
    reply = brain._gemini_direct_respond("Capital of France?")
    assert reply.engine == "gemini:gemini-3.5-flash"


def test_groq_backend_tags_its_engine(monkeypatch):
    from jarvis import llm

    monkeypatch.setattr(llm, "chat_available", lambda: True)
    monkeypatch.setattr(llm, "last_model", lambda: "openai/gpt-oss-120b")
    monkeypatch.setattr(llm, "chat_groq", lambda prompt, system=None, max_tokens=90, **kwargs: "Tokyo, sir.")
    reply = brain._groq_respond("Capital of Japan?")
    assert reply.engine == "groq:openai/gpt-oss-120b"


def test_daemon_command_payload_reports_engine_and_timing(monkeypatch):
    """The /api/command handler must tell the UI which model answered."""
    from jarvis import daemon

    monkeypatch.setattr(
        daemon,
        "respond",
        lambda text, image=None: Reply(speech="Tokyo, sir.", engine="gemini:gemini-2.5-flash"),
    )

    sent = {}

    class FakeHandler(daemon.JarvisDaemonHandler):
        def __init__(self):  # bypass the socket plumbing
            pass

        def _send_json(self, status, data):
            sent["status"] = status
            sent["data"] = data

        def log_message(self, *args, **kwargs):
            pass

    handler = FakeHandler()
    handler.do_POST = daemon.JarvisDaemonHandler.do_POST.__get__(handler, FakeHandler)

    class FakeReader:
        def __init__(self, body):
            self._body = body

        def read(self, _n):
            return self._body

    import io
    import json

    body = json.dumps({"text": "Capital of Japan?"}).encode("utf-8")
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = FakeReader(body)
    handler.path = "/api/command"

    handler.do_POST()

    assert sent["status"] == 200
    data = sent["data"]
    assert data["ok"] is True
    assert data["engine"] == "gemini:gemini-2.5-flash"
    assert data["elapsed_ms"] >= 0
    assert data["reply"]["speech"] == "Tokyo, sir."
