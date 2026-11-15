"""Tests for the Meta Quest USB-link helpers in the daemon."""
import subprocess

from jarvis import daemon


class _Proc:
    def __init__(self, stdout):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


def _fake_run(stdout_map):
    def run(cmd, *args, **kwargs):
        key = cmd[1] if len(cmd) > 1 else ""
        return _Proc(stdout_map.get(key, ""))

    return run


def test_find_adb_returns_path_or_none(monkeypatch):
    monkeypatch.setattr(daemon, "_find_adb", lambda: None)
    assert daemon._find_adb() is None


def test_quest_link_info_without_adb(monkeypatch):
    monkeypatch.setattr(daemon, "_find_adb", lambda: None)
    info = daemon._quest_link_info()
    assert info["installed"] is False
    assert info["devices"] == []
    assert info["reverse"] is False
    assert "adb" in info["hint"].lower()


def test_quest_link_info_with_device_and_reverse(monkeypatch):
    monkeypatch.setattr(daemon, "_find_adb", lambda: "C:/adb/adb.exe")
    monkeypatch.setattr(
        subprocess,
        "run",
        _fake_run({
            "devices": "List of devices attached\nABCD1234\tdevice\n",
            "reverse": "ABCD1234 tcp:8765 tcp:8765\n",
        }),
    )
    info = daemon._quest_link_info()
    assert info["installed"] is True
    assert info["devices"] == [{"serial": "ABCD1234", "state": "device"}]
    assert info["reverse"] is True


def test_quest_link_info_without_reverse(monkeypatch):
    monkeypatch.setattr(daemon, "_find_adb", lambda: "C:/adb/adb.exe")
    monkeypatch.setattr(
        subprocess,
        "run",
        _fake_run({"devices": "List of devices attached\n", "reverse": ""}),
    )
    info = daemon._quest_link_info()
    assert info["installed"] is True
    assert info["devices"] == []
    assert info["reverse"] is False
    assert "connect-quest.bat" in info["hint"]


def test_quest_link_info_unauthorized_device(monkeypatch):
    monkeypatch.setattr(daemon, "_find_adb", lambda: "C:/adb/adb.exe")
    monkeypatch.setattr(
        subprocess,
        "run",
        _fake_run({
            "devices": "List of devices attached\nABCD1234\tunauthorized\n",
            "reverse": "",
        }),
    )
    info = daemon._quest_link_info()
    assert info["devices"][0]["state"] == "unauthorized"
    assert info["reverse"] is False
