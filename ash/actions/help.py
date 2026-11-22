""""What can you do?" -- a short spoken tour, generated from the skill
catalog (ash/skills/catalog.py), so it can't fall out of date as
commands are added."""
import logging

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.registry.schema import Registry


def handle_help(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    from ash.skills.catalog import ASSISTANT
    from ash.skills.registry import categories

    # One short "Category: 'example'." per group -- easier to follow by
    # ear than one long list. Ash's own controls ("stop", "help") are
    # left out: you already found help.
    parts = []
    for category, skills in categories().items():
        example = next((s.examples[0] for s in skills if s.examples), None)
        if example and category != ASSISTANT:
            parts.append(f"{category}: '{example}'.")
    tts.say("Here's what I can do. " + " ".join(parts) +
            " Everything stays on this PC unless you've allowed a feature that needs the internet.")
    return HandlerResult()
