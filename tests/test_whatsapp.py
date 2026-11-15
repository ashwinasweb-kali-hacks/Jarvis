"""Tests for the WhatsApp driver, the allowlist and the messaging intents."""
from __future__ import annotations

import pytest

from jarvis import pc_intents, wa
from jarvis.tools.whatsapp import WhatsAppTool


# ------------------------------------------------------------------- numbers
@pytest.mark.parametrize("raw,expected", [
    ("9876543210", "+919876543210"),
    ("+91 98765 43210", "+919876543210"),
    ("+91-98765-43210", "+919876543210"),
    ("9123456789", "+919123456789"),
    ("(082) 98765 43210", "+919876543210"),
])
def test_normalize_number(raw, expected):
    assert wa.normalize_number(raw) == expected


def test_looks_like_number():
    assert wa.looks_like_number("9876543210") is True
    assert wa.looks_like_number("+91 98765 43210") is True
    assert wa.looks_like_number("santhosh") is False


# ----------------------------------------------------------------- allowlist
def test_only_the_owner_numbers_are_allowed(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_WHATSAPP_ALLOWED_NUMBERS", "9876543210,9123456789")
    allowed = wa.allowed_numbers()
    assert "+919876543210" in allowed
    assert "+919123456789" in allowed
    assert len(allowed) == 2


def test_random_numbers_are_refused(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_WHATSAPP_ALLOWED_NUMBERS", "9876543210")
    assert wa.is_allowed("9876543210") is True
    assert wa.is_allowed("9999999999") is False
    guard = wa.allow_check("9999999999")
    assert guard["ok"] is False
    assert "not on your allowed list" in guard["error"]


def test_tool_refuses_to_send_outside_the_allowlist(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_WHATSAPP_ALLOWED_NUMBERS", "9876543210")
    tool = WhatsAppTool()
    out = tool.run(action="send_message", target="9999999999", text="hello")
    assert out["ok"] is False
    assert "not on your allowed list" in str(out.get("error") or out.get("message"))

    out = tool.run(action="call", target="9999999999")
    assert out["ok"] is False
    assert out.get("placed") is False


def test_allow_action_adds_a_number(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_WHATSAPP_ALLOWED_NUMBERS", "9876543210")
    written = {}

    def _fake_set(key, value):
        written[key] = value
        return {"ok": True}

    monkeypatch.setattr("jarvis.settings.set", _fake_set)
    tool = WhatsAppTool()
    out = tool.run(action="allow", number="9123456789")
    assert out["ok"] is True
    assert out["number"] == "+919123456789"
    # The real settings file must not be touched by a test.
    assert written.get("whatsapp_allowed_numbers") == ["+919876543210", "+919123456789"]


# ------------------------------------------------------------------- intents
@pytest.mark.parametrize("phrase,action,target,text", [
    ("call 9876543210", "call", "9876543210", None),
    ("call santhosh", "call", "santhosh", None),
    ("send a message to 9876543210 saying hello there", "send_message", "9876543210", "hello there"),
    ("message mom i am on my way", "send_message", "mom", "i am on my way"),
    ("text ravi meeting at 5", "send_message", "ravi", "meeting at 5"),
    ("whatsapp 9876543210 saying hi", "send_message", "9876543210", "hi"),
    ("read my unread messages", "unread_messages", None, None),
    ("what are my unread messages on whatsapp", "unread_messages", None, None),
    ("read my recent messages", "recent_messages", None, None),
    ("recent messages on whatsapp", "recent_messages", None, None),
    ("read messages from santhosh", "read_contact", "santhosh", None),
    ("what did mom say on whatsapp", "read_contact", "mom", None),
])
def test_whatsapp_intents(phrase, action, target, text):
    actions = pc_intents.detect(phrase)
    assert actions, phrase
    assert actions[0]["tool"] == "whatsapp"
    assert actions[0]["args"]["action"] == action
    if target is not None:
        assert actions[0]["args"]["target"] == target
    if text is not None:
        assert actions[0]["args"]["text"] == text


def test_unread_and_recent_parsing_mock(monkeypatch):
    mock_rows = [
        "+91 98200 11223 12:07 am You deleted this message",
        "+91 98200 11223 12:07 am",
        "2 unread messages bigbasket Wednesday ₹30/- added to account",
        "2 unread messages bigbasket Wednesday",
        "SANTHOSH Yesterday Photo",
        "SANTHOSH Yesterday",
    ]
    monkeypatch.setattr(wa, "find_window", lambda auto_open=False: True)
    monkeypatch.setattr(wa, "_chat_rows", lambda win: mock_rows)

    unreads = wa.get_unread_messages()
    assert unreads["ok"] is True
    assert unreads["count"] == 2
    assert "bigbasket" in unreads["message"]

    recent = wa.get_recent_messages()
    assert recent["ok"] is True
    assert recent["count"] == 3
    assert "SANTHOSH" in recent["message"]

    contact = wa.read_contact_message("santhosh")
    assert contact["ok"] is True
    assert "Photo" in contact["message"]


def test_allow_intent():
    actions = pc_intents.detect("allow 9123456789")
    assert actions[0]["tool"] == "whatsapp"
    assert actions[0]["args"]["action"] == "allow"
    assert "9123456789" in actions[0]["args"]["number"]


def test_demo_and_voip_calls_keep_their_own_route():
    """'call my friend' is the HUD demo, 'via globalfone' is the VoIP gateway."""
    assert pc_intents.detect("call my friend") == []
    assert pc_intents.detect("call 9876543210 via globalfone") == []


def test_plain_questions_are_not_whatsapp():
    assert pc_intents.detect("what is the capital of France") == []
    assert pc_intents.detect("who wrote hamlet") == []
