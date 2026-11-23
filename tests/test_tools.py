"""Ash's commands as local-AI tools (ash/nlu/tools.py)."""
from ash.nlu import tools
from ash.skills import registry as skills


def test_every_offered_command_becomes_a_described_tool():
    definitions = tools.tool_definitions(skills.classifiable_intents())
    assert [d["function"]["name"] for d in definitions] == list(skills.classifiable_intents())
    for definition in definitions:
        function = definition["function"]
        assert definition["type"] == "function" and function["description"]
        assert function["parameters"]["type"] == "object"


def test_only_commands_that_take_something_have_a_target():
    by_name = {d["function"]["name"]: d["function"] for d in tools.tool_definitions(skills.classifiable_intents())}
    assert by_name["timer_set"]["parameters"]["required"] == ["target"]
    assert "target" in by_name["timer_set"]["parameters"]["properties"]
    assert by_name["media_pause"]["parameters"]["properties"] == {}
    assert 'Example: "set a timer for 10 minutes"' in by_name["timer_set"]["description"]


def test_the_definitions_stay_compact():
    """Every tool is read by the model on each request (on a CPU, every
    token costs time), so descriptions must stay short."""
    import json
    size = len(json.dumps(tools.tool_definitions(skills.classifiable_intents())))
    assert size < 18_000, f"{size} characters of tool definitions"


def test_an_invalid_call_cancels_the_whole_plan(monkeypatch):
    monkeypatch.setattr(tools, "chat", lambda *a, **k: {"tool_calls": [
        {"function": {"name": "media_pause", "arguments": {}}},
        {"function": {"name": "not_a_command", "arguments": {}}},
    ]})
    assert tools.plan("x", None, ("media_pause",), "", 1) is None
