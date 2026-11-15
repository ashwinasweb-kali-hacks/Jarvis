"""Tests for screen awareness, desktop input, workflows, approvals and mail.

The heavy system calls (UI Automation, OCR, SendInput, winget, Playwright) are
replaced with fakes: these tests pin the *contract* - what the assistant says and
what it refuses to do - without driving the real desktop.
"""
from __future__ import annotations

import pytest

from jarvis import approvals, desktop_input, pc_intents, screen, workflow
from jarvis.tools.pc_control import PCControlTool


# ------------------------------------------------------------------- desktop input
def test_click_needs_a_target_or_coordinates(monkeypatch):
    moved = {}
    monkeypatch.setattr(desktop_input, "move_mouse", lambda x, y, duration=0: moved.update({"x": x, "y": y}) or {"ok": True})
    monkeypatch.setattr(desktop_input, "_send", lambda *a, **k: None)
    monkeypatch.setattr(desktop_input, "cursor_position", lambda: {"x": 120, "y": 240})
    out = desktop_input.click(120, 240)
    assert out["ok"] is True
    assert moved == {"x": 120, "y": 240}


def test_click_rejects_an_unknown_button():
    out = desktop_input.click(1, 1, button="elbow")
    assert out["ok"] is False
    assert "left, right or middle" in out["error"]


def test_unknown_key_is_rejected():
    out = desktop_input.press("notakey")
    assert out["ok"] is False
    assert "unknown" in out["error"].lower()


def test_key_alias_resolution():
    assert desktop_input._vk_for("ctrl") == 0x11
    assert desktop_input._vk_for("esc") == 0x1B
    assert desktop_input._vk_for("enter") == 0x0D
    assert desktop_input._vk_for("F5") == 0x74


def test_type_text_sends_unicode_and_counts(monkeypatch):
    sent = {}
    monkeypatch.setattr(desktop_input, "_send", lambda *events: sent.update({"n": sent.get("n", 0) + len(events)}))
    out = desktop_input.type_text("héllo")
    assert out["ok"] is True
    assert out["characters"] == 5
    assert sent["n"] == 10  # down+up per character


def test_type_text_with_nothing_to_type_is_a_no_op(monkeypatch):
    monkeypatch.setattr(desktop_input, "_send", lambda *events: pytest.fail("nothing to send"))
    out = desktop_input.type_text("")
    assert out["ok"] is True
    assert out["characters"] == 0


def test_desktop_metrics_are_sane():
    metrics = desktop_input.screen_metrics()
    assert metrics["width"] >= 800 and metrics["height"] >= 600
    windows = desktop_input.list_windows()
    assert isinstance(windows, list)
    for win in windows[:5]:
        assert "title" in win and "hwnd" in win


# ---------------------------------------------------------------------- screen
SNAPSHOT = {
    "window": {"title": "Notepad", "hwnd": 42, "pid": 7, "rect": {"x": 100, "y": 50, "width": 800, "height": 600}},
    "elements": [
        {"name": "Save", "type": "Button", "center": [40, 32], "x": 10, "y": 20, "width": 60, "height": 24},
        {"name": "File", "type": "MenuItem", "center": [25, 15], "x": 5, "y": 5, "width": 40, "height": 20},
    ],
    "element_count": 2,
    "text": "Hello world\nsecond line",
    "lines": [{"text": "Hello world", "box": [10, 60, 120, 20]}],
    "elapsed_ms": 120,
}


def test_describe_summarises_without_reading_everything():
    spoken = screen.describe(SNAPSHOT)
    assert "Notepad" in spoken
    assert "Save" in spoken
    assert spoken.count("Save") == 1


def test_describe_handles_missing_window():
    assert "desktop" in screen.describe({"window": None, "elements": [], "text": ""}).lower()


def test_find_matches_element_names():
    hit = screen.find("save", SNAPSHOT)
    assert hit and hit["name"] == "Save"
    assert screen.find("file", SNAPSHOT)["name"] == "File"
    assert screen.find("nonexistent widget", SNAPSHOT) is None


def test_find_offsets_ocr_lines_by_the_capture_rect():
    """UIA rectangles are already absolute; OCR boxes are window-relative."""
    data = {
        "window": {"title": "Notepad", "hwnd": 0, "rect": {"x": 100, "y": 50, "width": 800, "height": 600}},
        "elements": [],
        "lines": [{"text": "Save", "box": [10, 20, 60, 24]}],
        "bbox": (100, 50, 900, 650),
        "text": "Save",
    }
    hit = screen.find("save", data)
    assert hit and hit["source"] == "ocr"
    assert hit["center"] == [100 + 10 + 30, 50 + 20 + 12]


def test_click_element_clicks_the_element_centre(monkeypatch):
    snap = dict(SNAPSHOT, window={"title": "Notepad", "hwnd": 0,
                                  "rect": {"x": 100, "y": 50, "width": 800, "height": 600}})
    clicked = {}
    monkeypatch.setattr(screen, "snapshot", lambda **kwargs: snap)
    monkeypatch.setattr(desktop_input, "click", lambda x, y, **k: clicked.update({"x": x, "y": y}) or {"ok": True})
    out = screen.click_element("save")
    assert out["ok"] is True and out["via"] == "mouse"
    assert clicked == {"x": 10 + 30, "y": 20 + 12}


def test_click_element_reports_a_missing_target(monkeypatch):
    monkeypatch.setattr(screen, "snapshot", lambda **kwargs: SNAPSHOT)
    out = screen.click_element("does not exist")
    assert out["ok"] is False
    assert "cannot see" in out["error"].lower()


def test_vision_is_only_used_on_request(monkeypatch):
    called = {"vision": 0}
    monkeypatch.setattr(screen, "screenshot_bytes", lambda: b"\x89PNG fake")
    import jarvis.vision as vision

    monkeypatch.setattr(vision, "describe_image",
                        lambda image, prompt=None: called.__setitem__("vision", called["vision"] + 1) or {
                            "ok": True, "description": "a window"})
    out = screen.describe_with_vision("what is this")
    assert out["ok"] is True
    assert out["description"] == "a window"
    assert called["vision"] == 1


# -------------------------------------------------------------------- workflow
def test_workflow_runs_safe_steps(monkeypatch):
    monkeypatch.setattr(workflow, "_run_wait", lambda step: {"ok": True, "waited": 0.0, "_ok": True})
    out = workflow.run([{"tool": "wait", "seconds": 0}])
    assert out["ok"] is True
    assert out["performed"] == 1


def test_workflow_stops_at_destructive_step(monkeypatch):
    workflow.clear_pending()
    called = {"wait": 0}
    monkeypatch.setattr(workflow, "_run_wait", lambda step: called.__setitem__("wait", called["wait"] + 1) or {"ok": True, "_ok": True})
    out = workflow.run([
        {"tool": "wait", "seconds": 0},
        {"tool": "pc_control", "action": "delete_file", "path": r"E:\tmp\x.txt"},
    ])
    assert out["ok"] is False
    assert out.get("needs_confirmation") is True
    assert called["wait"] == 0, "nothing may run before the user confirms"
    assert workflow.pending()["pending"] is True
    workflow.clear_pending()


def test_workflow_confirm_is_gated_and_cancellable():
    workflow.clear_pending()
    assert workflow.confirm()["ok"] is False
    workflow.clear_pending()


def test_workflow_stops_on_failure(monkeypatch):
    def boom(step):
        return {"ok": False, "error": "nope", "_ok": False}

    monkeypatch.setitem(workflow.RUNNERS, "wait", boom)
    out = workflow.run([{"tool": "wait"}, {"tool": "wait"}])
    assert out["ok"] is False
    assert out["performed"] == 1
    assert "stopped" in out["summary"].lower()


def test_workflow_rejects_empty_and_oversized():
    assert workflow.run([])["ok"] is False
    assert workflow.run([{"tool": "wait"}] * (workflow.MAX_STEPS + 1))["ok"] is False


def test_workflow_parallel_batch(monkeypatch):
    monkeypatch.setattr(workflow, "_run_wait", lambda step: {"ok": True, "_ok": True})
    out = workflow.run([{"action": "parallel", "tool": "wait", "steps": [{"tool": "wait", "seconds": 0}, {"tool": "wait", "seconds": 0}]}])
    assert out["ok"] is True
    assert out["performed"] == 2


# -------------------------------------------------------------------- approvals
@pytest.fixture(autouse=True)
def clean_approvals():
    approvals.cancel()
    workflow.clear_pending()
    yield
    approvals.cancel()
    workflow.clear_pending()


def test_affirmative_and_negative_parsing():
    for word in ("yes", "Yes sir.", "confirm", "go ahead", "do it"):
        assert approvals.is_affirmative(word), word
    for word in ("no", "cancel", "forget it", "not now"):
        assert approvals.is_negative(word), word
    assert approvals.is_affirmative("what is the weather") is False


def test_needs_confirmation_for_destructive_host_actions(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_CONFIRM_DESTRUCTIVE", "1")
    assert approvals.needs_confirmation("pc_control", {"action": "delete_file"}) is True
    assert approvals.needs_confirmation("pc_control", {"action": "uninstall_app"}) is True
    assert approvals.needs_confirmation("pc_control", {"action": "shutdown"}) is True
    assert approvals.needs_confirmation("pc_control", {"action": "open_app"}) is False
    assert approvals.needs_confirmation("pc_control", {"action": "screen"}) is False


def test_dangerous_shell_is_gated_but_a_read_is_not():
    assert approvals.needs_confirmation("pc_control", {"action": "run_powershell", "command": "format C: /q"}) is True
    assert approvals.needs_confirmation("pc_control", {"action": "run_powershell", "command": "Get-Date"}) is False


def test_request_then_confirm_runs_once(monkeypatch):
    import time as _t

    tmp = None
    runs = {"count": 0}

    def fake_execute(tool, args=None, confirmed=False):
        runs["count"] += 1
        runs["confirmed"] = confirmed
        return {"ok": True, "result": {"ok": True, "message": "deleted"}}

    monkeypatch.setattr("jarvis.tools.base.get_default_registry", lambda: type("R", (), {"execute": staticmethod(fake_execute)})())
    approvals.request("pc_control", {"action": "delete_file", "path": r"E:\tmp\x.txt"})
    assert approvals.pending()["pending"] is True
    out = approvals.confirm()
    assert out["ok"] is True
    assert runs == {"count": 1, "confirmed": True}
    assert approvals.pending()["pending"] is False
    # A second yes must not re-run a finished action.
    again = approvals.confirm()
    assert again["ok"] is False
    assert runs["count"] == 1


def test_confirm_without_a_request_is_harmless():
    out = approvals.confirm()
    assert out["ok"] is False
    assert "nothing" in out["speech"].lower()


# ---------------------------------------------------------------- tool surface
def test_screen_action_uses_local_ocr(monkeypatch):
    monkeypatch.setattr(screen, "snapshot", lambda with_ocr=True, window=None: SNAPSHOT)
    out = PCControlTool().run(action="screen", target="describe")
    assert out["ok"] is True
    assert "Notepad" in out["message"]


def test_press_key_action_reports_unknown_keys():
    out = PCControlTool().run(action="press_key", keys="notarealkey")
    assert out["ok"] is False


def test_uninstall_requires_confirmation(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_CONFIRM_DESTRUCTIVE", "1")
    out = PCControlTool().run(action="uninstall_app", package="spotify")
    assert out["ok"] is False
    assert out.get("needs_confirmation") is True


def test_run_powershell_refuses_dangerous_commands(monkeypatch):
    monkeypatch.setenv("JARVIS_SETTING_CONFIRM_DESTRUCTIVE", "1")
    out = PCControlTool().run(action="run_powershell", command="Remove-Item -Recurse -Force E:\\x")
    assert out["ok"] is False
    assert out.get("needs_confirmation") is True


def test_run_powershell_returns_real_output():
    out = PCControlTool().run(action="run_powershell", command="Write-Output 'jarvis-probe'", timeout=45)
    assert out["ok"] is True
    assert "jarvis-probe" in out["stdout"]


def test_workflow_action_requires_steps():
    out = PCControlTool().run(action="workflow", steps=[])
    assert out["ok"] is False


def test_install_and_uninstall_intents_use_real_actions():
    assert pc_intents.detect("install 7zip.7zip")[0]["args"]["action"] == "install_app"
    assert pc_intents.detect("uninstall spotify")[0]["args"]["action"] == "uninstall_app"


# ----------------------------------------------------------------------- mail
def test_mailbox_refuses_without_configuration(monkeypatch):
    from jarvis import mailbox

    monkeypatch.setattr(mailbox, "configured", lambda: {
        "configured": False, "address": "", "smtp": "", "imap": "", "password_set": False,
        "calendar_configured": False, "missing": ["email_address", "email_smtp_host"],
    })
    out = mailbox.send("a@b.com", "hi", "body")
    assert out["ok"] is False
    assert out.get("not_configured") is True

    note = mailbox.calendar()
    assert note["ok"] is False and note.get("not_configured") is True


def test_mailbox_rejects_a_bad_address(monkeypatch):
    from jarvis import mailbox

    monkeypatch.setattr(mailbox, "configured", lambda: {
        "configured": True, "address": "me@example.com", "smtp": "smtp.example.com",
        "imap": "", "password_set": True, "calendar_configured": False, "missing": [],
    })
    out = mailbox.send("not-an-address", "hi", "body")
    assert out["ok"] is False
    assert "email address" in out["error"]


def test_calendar_parses_a_local_feed(monkeypatch, tmp_path):
    from jarvis import mailbox

    ics = tmp_path / "today.ics"
    ics.write_text(
        "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:Standup\r\n"
        "DTSTART:20990101T090000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mailbox, "_setting", lambda key, default=None: ics.as_uri() if key == "calendar_ics_url" else default)
    # A far-future event is outside the window, so the feed parses but is empty.
    out = mailbox.calendar(days=1)
    assert out["ok"] is True
    assert out["count"] == 0
    assert out["message"] == "Nothing on your calendar."
