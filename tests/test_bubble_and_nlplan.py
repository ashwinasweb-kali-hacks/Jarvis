import json
from jarvis import bubblectl, nlplan, pc_intents
from jarvis import brain


def test_nlplan_looks_actionable():
    assert nlplan.looks_actionable("open notepad and write hello") is True
    assert nlplan.looks_actionable("can you launch chrome") is True
    assert nlplan.looks_actionable("please turn the volume up") is True
    assert nlplan.looks_actionable("take a screenshot right now") is True
    assert nlplan.looks_actionable("search for latest ai news") is True

    # Questions and general chat should NOT be planned
    assert nlplan.looks_actionable("what is 2 + 2?") is False
    assert nlplan.looks_actionable("who is the president?") is False
    assert nlplan.looks_actionable("how does photosynthesis work?") is False
    assert nlplan.looks_actionable("tell me about quantum computing") is False


def test_nlplan_normalise_whitelist():
    raw = {
        "speech": "Opening notepad and writing notes, sir.",
        "actions": [
            {"action": "open_app", "args": {"target": "notepad"}},
            {"action": "type_text", "args": {"text": "hello world"}},
            {"action": "format_c_drive", "args": {"force": True}},  # Hallucinated/forbidden -> dropped
            {"action": "screenshot", "extra_bad_arg": "ignored"},
        ]
    }
    norm = nlplan._normalise(raw)
    assert norm is not None
    assert norm["speech"] == "Opening notepad and writing notes, sir."
    assert len(norm["actions"]) == 3
    assert norm["actions"][0]["args"]["action"] == "open_app"
    assert norm["actions"][0]["args"]["target"] == "notepad"
    assert norm["actions"][1]["args"]["action"] == "type_text"
    assert norm["actions"][1]["args"]["text"] == "hello world"
    assert norm["actions"][2]["args"]["action"] == "screenshot"


def test_nlplan_plan_mock(monkeypatch):
    sample_json = json.dumps({
        "speech": "Opening Spotify, sir.",
        "actions": [{"action": "open_app", "args": {"target": "spotify"}}]
    })
    monkeypatch.setattr(nlplan, "_ask_cloud", lambda text: (sample_json, "gemini:mock"))
    res = nlplan.plan("launch spotify on my pc")
    assert res is not None
    assert res["speech"] == "Opening Spotify, sir."
    assert len(res["actions"]) == 1
    assert res["actions"][0]["args"] == {"action": "open_app", "target": "spotify"}
    assert "planner:gemini:mock" in res["engine"]


def test_pc_intents_bubble_voice_commands():
    assert pc_intents.detect("open bubble") == [{"tool": "pc_control", "args": {"action": "bubble", "target": "open"}}]
    assert pc_intents.detect("start dynamic island") == [{"tool": "pc_control", "args": {"action": "bubble", "target": "open"}}]
    assert pc_intents.detect("show popup mode") == [{"tool": "pc_control", "args": {"action": "bubble", "target": "open"}}]
    assert pc_intents.detect("close the bubble") == [{"tool": "pc_control", "args": {"action": "bubble", "target": "close"}}]
    assert pc_intents.detect("toggle dynamic island") == [{"tool": "pc_control", "args": {"action": "bubble", "target": "toggle"}}]

    speech = pc_intents.spoken_intent([{"tool": "pc_control", "args": {"action": "bubble", "target": "open"}}])
    assert "Opening the dynamic island bubble" in speech

    speech_close = pc_intents.spoken_intent([{"tool": "pc_control", "args": {"action": "bubble", "target": "close"}}])
    assert "Closing the bubble" in speech_close


def test_bubblectl_status():
    st = bubblectl.status()
    assert st["ok"] is True
    assert "running" in st
    assert "python" in st
    assert st["lock_port"] == 8799


def test_brain_planner_integration(monkeypatch):
    sample_plan = {
        "speech": "Searching for quantum computing, sir.",
        "actions": [{"tool": "pc_control", "args": {"action": "browser", "query": "quantum computing"}}],
        "engine": "planner:test",
    }
    monkeypatch.setattr(nlplan, "maybe_plan", lambda text: sample_plan if "research" in text else None)

    reply = brain.respond("can you research quantum computing for my project")
    assert "quantum" in reply.speech.lower()
    assert reply.engine == "planner:test"
    assert len(reply.actions) == 1
    assert reply.actions[0]["args"]["action"] == "browser"


def test_window_control_intents():
    max_act = pc_intents.detect("can you please maximize this window")
    assert len(max_act) == 1
    assert max_act[0]["args"]["action"] == "maximize_window"
    assert "Maximizing" in pc_intents.spoken_intent(max_act)

    min_act = pc_intents.detect("minimize the active window")
    assert len(min_act) == 1
    assert min_act[0]["args"]["action"] == "minimize_window"
    assert "Minimizing" in pc_intents.spoken_intent(min_act)

    close_act = pc_intents.detect("close this window please")
    assert len(close_act) == 1
    assert close_act[0]["args"]["action"] == "close_window"
    assert "Closing" in pc_intents.spoken_intent(close_act)


def test_browser_tab_control_intents():
    dups = pc_intents.detect("close duplicate tabs in the browser")
    assert len(dups) == 1
    assert dups[0]["args"]["action"] == "browser"
    assert dups[0]["args"]["browser_action"] == "close_duplicate_tabs"
    assert "Closing duplicate tabs" in pc_intents.spoken_intent(dups)

    open_tab = pc_intents.detect("open a new tab")
    assert len(open_tab) == 1
    assert open_tab[0]["args"]["action"] == "browser"
    assert open_tab[0]["args"]["browser_action"] == "open_tab"
    assert "Opening a new tab" in pc_intents.spoken_intent(open_tab)

    close_tab = pc_intents.detect("close this tab")
    assert len(close_tab) == 1
    assert close_tab[0]["args"]["action"] == "browser"
    assert close_tab[0]["args"]["browser_action"] == "close_tab"
    assert "Closing the tab" in pc_intents.spoken_intent(close_tab)

    list_tabs = pc_intents.detect("list all open tabs")
    assert len(list_tabs) == 1
    assert list_tabs[0]["args"]["action"] == "browser"
    assert list_tabs[0]["args"]["browser_action"] == "list_tabs"

    reload_tab = pc_intents.detect("refresh the page")
    assert len(reload_tab) == 1
    assert reload_tab[0]["args"]["action"] == "browser"
    assert reload_tab[0]["args"]["browser_action"] == "reload"


def test_live_browse_president_mock(monkeypatch):
    mock_search = {
        "ok": True,
        "results": [
            {"title": "President of the United States", "snippet": "Donald Trump is the 47th and current president since January 20, 2025."},
            {"title": "White House", "snippet": "President Donald J. Trump leads the nation."}
        ]
    }
    from jarvis.tools.pc_control import PCControlTool
    monkeypatch.setattr(PCControlTool, "run", lambda self, action, target, **kw: mock_search if action == "web_search" else {})

    reply = brain.respond("search for the current president in usa")
    assert reply is not None
    assert "search:" in reply.engine
    assert "Trump" in reply.speech or "president" in reply.speech.lower()
