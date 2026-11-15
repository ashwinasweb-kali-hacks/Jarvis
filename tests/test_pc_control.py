"""Tests for full host control: the pc_control tool and the intent parser."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis import brain, pc_intents
from jarvis.tools.pc_control import PCControlTool, control_enabled, full_access, resolve_path


# --------------------------------------------------------------------- intents
@pytest.mark.parametrize("phrase,action,key,value", [
    ("open chrome", "open_app", "target", "chrome"),
    ("launch notepad", "open_app", "target", "notepad"),
    ("close chrome", "close_app", "target", "chrome"),
    ("kill process notepad.exe", "kill_process", "target", "notepad.exe"),
    ("open https://github.com", "open_url", "target", "https://github.com"),
    ("go to wikipedia.org", "open_url", "target", "wikipedia.org"),
    ("lock the pc", "lock_screen", None, None),
    ("shut down the pc", "shutdown", "delay_seconds", 5),
    ("restart the pc", "restart", "delay_seconds", 5),
    ("cancel the shutdown", "cancel_shutdown", None, None),
    ("take a screenshot", "screenshot", None, None),
    ("turn up the volume", "volume", "target", "volume_up"),
    ("mute the audio", "volume", "target", "mute"),
    ("list processes", "list_processes", None, None),
    ("system info", "system_info", None, None),
    ("run the command dir", "run_command", "target", "dir"),
])
def test_intent_parsing(phrase, action, key, value):
    actions = pc_intents.detect(phrase)
    assert actions, phrase
    assert actions[0]["tool"] == "pc_control"
    args = actions[0]["args"]
    assert args["action"] == action
    if key:
        assert args[key] == value


def test_intent_keeps_windows_path_case():
    actions = pc_intents.detect(r"read the file C:\Users\avi10\Notes.txt")
    assert actions[0]["args"]["path"] == r"C:\Users\avi10\Notes.txt"


def test_intent_write_file_content():
    actions = pc_intents.detect(r"write file C:\Users\avi10\test.txt with content hello world")
    args = actions[0]["args"]
    assert args["action"] == "write_file"
    assert args["path"] == r"C:\Users\avi10\test.txt"
    assert args["content"] == "hello world"


def test_intent_open_file_is_not_read():
    actions = pc_intents.detect(r"open the file C:\Users\avi10\Notes.txt")
    assert actions[0]["args"]["action"] == "open_file"


@pytest.mark.parametrize("phrase", [
    "what is the capital of France?",
    "who wrote hamlet",
    "tell me a joke",
    "thanks jarvis",
])
def test_plain_questions_do_not_trigger_pc_actions(phrase):
    assert pc_intents.detect(phrase) == []


@pytest.mark.parametrize("phrase", [
    "close help",
    "exit vr",
    "show the core",
    "switch to friday",
])
def test_ui_commands_are_not_pc_actions(phrase):
    assert pc_intents.detect(phrase) == []


def test_spoken_intent_is_meaningful():
    actions = pc_intents.detect("open notepad")
    assert "notepad" in pc_intents.spoken_intent(actions).lower()
    actions = pc_intents.detect("lock the pc")
    assert "lock" in pc_intents.spoken_intent(actions).lower()


def test_pc_command_does_not_spend_a_model_request(monkeypatch):
    """Host control is answered locally: no Gemini/Groq call."""
    monkeypatch.setenv("JARVIS_SETTING_PC_CONTROL_ENABLED", "1")

    def _trap(*_a, **_k):  # pragma: no cover - must never run
        raise AssertionError("a PC command must not reach a model")

    monkeypatch.setattr(brain, "_oauth_respond", _trap)
    monkeypatch.setattr(brain, "_gemini_direct_respond", _trap)
    monkeypatch.setattr(brain, "_groq_respond", _trap)

    reply = brain.respond("take a screenshot")
    assert reply.engine == "pc-control"
    assert reply.actions and reply.actions[0]["tool"] == "pc_control"


# ----------------------------------------------------------------------- tool
def test_write_then_read_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_SETTING_PC_CONTROL_ENABLED", "1")
    monkeypatch.setenv("JARVIS_SETTING_PC_FULL_ACCESS", "1")
    tool = PCControlTool()
    target = tmp_path / "note.txt"

    out = tool.run(action="write_file", path=str(target), content="hello sir")
    assert out["ok"] is True
    assert target.read_text(encoding="utf-8") == "hello sir"

    out = tool.run(action="read_file", path=str(target))
    assert out["ok"] is True
    assert out["content"] == "hello sir"


def test_append_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_SETTING_PC_CONTROL_ENABLED", "1")
    tool = PCControlTool()
    target = tmp_path / "log.txt"
    tool.run(action="write_file", path=str(target), content="one\n")
    tool.run(action="write_file", path=str(target), content="two\n", mode="append")
    assert target.read_text(encoding="utf-8") == "one\ntwo\n"


def test_list_dir_and_search(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_SETTING_PC_CONTROL_ENABLED", "1")
    monkeypatch.setenv("JARVIS_SETTING_PC_FULL_ACCESS", "1")
    tool = PCControlTool()
    (tmp_path / "report.txt").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()

    out = tool.run(action="list_dir", path=str(tmp_path))
    names = {e["name"] for e in out["entries"]}
    assert "report.txt" in names and "sub" in names

    out = tool.run(action="search_files", path=str(tmp_path), target="report")
    assert out["count"] >= 1
    assert any(m["name"] == "report.txt" for m in out["matches"])


def test_delete_file(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_SETTING_PC_CONTROL_ENABLED", "1")
    monkeypatch.setenv("JARVIS_SETTING_PC_FULL_ACCESS", "1")
    tool = PCControlTool()
    target = tmp_path / "temp.txt"
    target.write_text("bye", encoding="utf-8")
    # Permanent deletion is gated: without a yes nothing is removed.
    refused = tool.run(action="delete_file", path=str(target))
    assert refused["ok"] is False
    assert refused.get("needs_confirmation") is True
    assert target.exists()

    out = tool.run(action="delete_file", path=str(target), confirm=True)
    assert out["ok"] is True
    assert not target.exists()


def test_master_switch_blocks_everything(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_SETTING_PC_CONTROL_ENABLED", "0")
    tool = PCControlTool()
    out = tool.run(action="write_file", path=str(tmp_path / "x.txt"), content="nope")
    assert out["ok"] is False
    assert out.get("status") == "blocked"


def test_full_access_off_confines_to_home(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_PC_FULL_ACCESS", "0")
    assert full_access() is False
    with pytest.raises(PermissionError):
        resolve_path(r"C:\ProgramData\jarvis-outside-home.txt")
    # inside the home folder it is still allowed
    assert resolve_path(str(Path.home() / "jarvis-inside-home.txt"))


def test_system_paths_are_protected(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_PC_FULL_ACCESS", "1")
    monkeypatch.setenv("JARVIS_SETTING_PC_BLOCK_SYSTEM_PATHS", "1")
    tool = PCControlTool()
    out = tool.run(action="write_file", path=r"C:\Windows\jarvis-test.txt", content="x")
    assert out["ok"] is False
    assert "protected system path" in str(out.get("error") or "")


def test_run_command_captures_output(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_PC_CONTROL_ENABLED", "1")
    tool = PCControlTool()
    out = tool.run(action="run_command", target="echo jarvis", timeout=20)
    assert out["ok"] is True
    assert "jarvis" in out["stdout"].lower()


def test_system_info_and_processes(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_PC_CONTROL_ENABLED", "1")
    tool = PCControlTool()
    info = tool.run(action="system_info")
    assert info["ok"] is True
    assert "os" in info["info"]
    procs = tool.run(action="list_processes")
    assert procs["ok"] is True
    assert isinstance(procs["processes"], list)


# ---------------------------------------------------------------------- brain
def test_brain_attaches_pc_actions(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_PC_CONTROL_ENABLED", "1")
    reply = brain.respond("take a screenshot")
    assert any(a.get("tool") == "pc_control" for a in reply.actions)


def test_pc_actions_work_while_the_brain_is_off(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_BRAIN_ENABLED", "0")
    monkeypatch.setenv("JARVIS_SETTING_PC_CONTROL_ENABLED", "1")
    reply = brain.respond("take a screenshot")
    assert reply.engine == "brain-off"
    assert any(a.get("tool") == "pc_control" for a in reply.actions)


def test_pc_control_disabled_means_no_actions(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_PC_CONTROL_ENABLED", "0")
    reply = brain.respond("take a screenshot")
    assert not any(a.get("tool") == "pc_control" for a in reply.actions)
