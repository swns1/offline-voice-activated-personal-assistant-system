"""Ash's commands as tools for the local AI (Ollama's native tool
calling), generated from the skill catalog (ash/skills/catalog.py), so
the AI's view of what Ash can do is never out of date.

The rule-based grammar stays the first, fast path for every command;
this is only used when it can't help:
- loose phrasing the grammar doesn't match ("make it a bit quieter"):
  ash/actions/semantic_fallback.py
- several steps in one sentence ("open Spotify, then set a timer for 10
  minutes"): ash/actions/chain.py

Whatever the model asks for is checked before anything runs: it must
name one of the tools it was offered, with a text target. Commands it
picks still go through the dispatcher's usual confirmation gates.
"""
import json

from ash.config import Config
from ash.nlu.intents import ParsedCommand
from ash.skills import registry as skills
from ash.utils.ollama import chat

_TARGET = {"type": "string", "description": "What it acts on, in the user's words."}


def tool_definitions(intents: tuple[str, ...]) -> list[dict]:
    """One function per command: its name, what it does, an example, and
    a `target` parameter if it takes one. Kept short on purpose: every
    word here is read by the model on each request."""
    tools = []
    for intent in intents:
        skill = skills.get(intent)
        if skill is None:
            continue
        description = skill.description
        if skill.examples:
            description += f' Example: "{skill.examples[0]}".'
        parameters: dict = {"type": "object", "properties": {}}
        if skill.verbs:  # it's said with something after it: "set a timer for" + "10 minutes"
            parameters["properties"]["target"] = _TARGET
            if not skill.phrases:  # never said on its own
                parameters["required"] = ["target"]
        tools.append({"type": "function",
                      "function": {"name": intent, "description": description, "parameters": parameters}})
    return tools


def _target(arguments) -> str | None:
    if isinstance(arguments, str):  # some models send the arguments as a JSON string
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except ValueError:
            return None
    if not isinstance(arguments, dict):
        return None
    target = arguments.get("target", "")
    if isinstance(target, bool):
        return None
    if isinstance(target, int | float):  # "set the volume to" 50
        target = str(target)
    return target if isinstance(target, str) else None


def plan(text: str, config: Config, intents: tuple[str, ...], system: str,
         timeout: float) -> list[ParsedCommand] | None:
    """The commands the model chose for `text`, in order, or None if it
    chose none -- or if any call is invalid, in which case none of them
    run (a half-understood request is safer ignored than half-done)."""
    message = chat(config, [{"role": "user", "content": text}], system=system,
                   tools=tool_definitions(intents), timeout=timeout)
    calls = message.get("tool_calls") or []
    commands = []
    for call in calls:
        function = call.get("function", {}) if isinstance(call, dict) else {}
        name = function.get("name")
        target = _target(function.get("arguments", {}))
        if name not in intents or target is None:
            return None
        commands.append(ParsedCommand(intent=name, target=target.strip()))
    return commands or None
