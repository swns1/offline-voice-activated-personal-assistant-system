"""Centralizes "should this action ask before doing it?" and how it asks,
so every risky action confirms the same way instead of each handler
hand-rolling its own ask-then-resume dance.

Every confirmation question follows one rule: say what will actually
happen -- including what you'd lose, if anything -- before asking "Are
you sure?". A bare "Are you sure?" doesn't tell you what you're agreeing
to.

Two entry points:
- Static per-intent gates (shutdown): declared as a skill's `confirm`
  in ash/skills/catalog.py. dispatch() and run_chain() check
  needs_confirmation() before calling the handler at all, and
  wrap_with_confirmation() asks the gate's question.
- Confirmations whose question depends on what's actually being done
  ("This will force Discord to quit...", "I'll click 'Save'...") are
  built inside the handler with ask_to_confirm(), once it knows the
  specifics.

With config.security.voice_gate_enabled, the returned HandlerResult
also sets requires_voice_match=True -- ash/main.py's loop checks the
raw audio of the answer against ash/security/voice_gate.py's enrolled
voiceprint before ever calling resume(), so a plain spoken "yes" alone
isn't enough. resume() itself doesn't need to know about any of this;
the voice check is a gate in front of it, not inside it.
"""
import logging
import re
from typing import Callable

from ash.actions.results import YES_NO, HandlerResult
from ash.privacy.redact import said
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.registry.schema import Registry
from ash.skills import registry as skills

Handler = Callable[[str, Registry, TtsWorker, logging.Logger, Config], HandlerResult | None]



# Matched after normalize_answer(), so "Yes." / "Yeah!" / "YES please"
# from speech-to-text all count.
AFFIRMATIVE_ANSWERS = {
    "yes", "yeah", "yep", "yes please", "confirm", "do it", "sure",
    "go ahead", "yes do it", "i'm sure", "yes i'm sure",
}


def normalize_answer(answer: str) -> str:
    """Lowercase, drop punctuation (speech-to-text writes "Yes." not
    "yes"), and collapse whitespace."""
    answer = re.sub(r"[^\w\s']", "", answer.lower())
    return " ".join(answer.split())


def is_affirmative(answer: str) -> bool:
    return normalize_answer(answer) in AFFIRMATIVE_ANSWERS


def needs_confirmation(intent: str) -> bool:
    return skills.confirmation_gate(intent) is not None


def ask_to_confirm(
    question: str, on_yes: Callable[[], HandlerResult | None], *,
    action: str, declined_reply: str,
    tts: TtsWorker, log: logging.Logger, config: Config,
) -> HandlerResult:
    """Ask `question`; run `on_yes` only if the answer is affirmative.
    Anything else -- "no", silence-turned-noise, an unclear answer -- is
    treated as no, since these are the actions that can't be undone."""
    def resume(answer: str) -> HandlerResult:
        if not is_affirmative(answer):
            log.info("Confirmation declined for %s: %s", action, said(answer))
            tts.say(declined_reply)
            return HandlerResult()
        result = on_yes()
        return result if result is not None else HandlerResult()

    return HandlerResult(
        done=False, question=question, resume=resume,
        requires_voice_match=config.security.voice_gate_enabled, choices=YES_NO,
    )


def wrap_with_confirmation(
    intent: str, handler: Handler, target: str,
    registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config,
) -> HandlerResult:
    gate = skills.confirmation_gate(intent)
    return ask_to_confirm(
        gate.question, lambda: handler(target, registry, tts, log, config),
        action=intent, declined_reply=gate.declined_reply,
        tts=tts, log=log, config=config,
    )
