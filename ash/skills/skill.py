"""What a skill (one voice command) declares about itself. See
ash/skills/catalog.py for the declarations and ash/skills/registry.py
for everything built from them."""
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ash.actions.results import HandlerResult
    from ash.audio.tts import TtsWorker
    from ash.config import Config
    from ash.registry.schema import Registry

Handler = Callable[[str, "Registry", "TtsWorker", logging.Logger, "Config"], "HandlerResult | None"]


@dataclass(frozen=True)
class Gate:
    """A fixed confirmation asked before the handler runs at all: what
    will happen, then "Are you sure?" -- and what to say on anything but
    a clear yes. (Confirmations that depend on specifics, like which
    program "close X" would force-quit, are asked by the handler itself.)"""
    question: str
    declined_reply: str


@dataclass(frozen=True)
class Skill:
    intent: str
    handler: Handler
    category: str
    # One line, for "what can you do", the GUI help page, and the local AI.
    description: str
    examples: tuple[str, ...] = ()
    # Spoken prefixes followed by a target: "set a timer for" + "5 minutes".
    verbs: tuple[str, ...] = ()
    # Whole utterances with no target: "pause", "what's on my calendar".
    phrases: tuple[str, ...] = ()
    confirm: Gate | None = None
    # May be a step in a multi-step command the local AI breaks down
    # ("open spotify and then set a timer").
    chainable: bool = False
    # The local AI may map loosely phrased speech onto it ("turn it down a
    # bit" -> volume_down) when no phrase matched.
    classifiable: bool = False
    # Online features it may use (keys of ash/privacy/egress.py FEATURES).
    online: tuple[str, ...] = ()
    # Internal routing only: no phrases, not listed in help.
    hidden: bool = False
