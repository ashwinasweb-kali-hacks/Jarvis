from jarvis.tools.pc_automation import PCAutomationTool
from jarvis.brain import respond


def test_pc_automation_tool_registered():
    tool = PCAutomationTool()
    assert tool.name == "pc_automation"
    assert tool.risk == "safe"


def test_brain_automation_intents():
    """Host intents now route through the fuller pc_control tool."""
    reply = respond("open notepad")
    assert "notepad" in reply.speech.lower()
    assert any(a["tool"] == "pc_control" and a["args"].get("target") == "notepad" for a in reply.actions)

    reply_calc = respond("open calculator")
    assert "calculator" in reply_calc.speech.lower()
    assert any(a["tool"] == "pc_control" and a["args"].get("target") == "calculator" for a in reply_calc.actions)

    reply_vol = respond("volume up")
    assert "volume" in reply_vol.speech.lower()
    assert any(
        a["tool"] == "pc_control"
        and a["args"].get("action") == "volume"
        and a["args"].get("target") == "volume_up"
        for a in reply_vol.actions
    )


def test_legacy_pc_automation_actions_are_not_duplicated():
    """The old tool must not run alongside the new one for the same request."""
    reply = respond("take a screenshot")
    assert not any(a["tool"] == "pc_automation" for a in reply.actions)
    assert any(a["tool"] == "pc_control" for a in reply.actions)
