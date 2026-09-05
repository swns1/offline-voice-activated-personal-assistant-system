"""Fallback conversational "brain" via a local Ollama server -- reached
only from ash/actions/open_app.py's no-match branch (gated on
config.ollama.enabled), not through its own grammar verb or dispatcher
entry. No special trigger phrase needed: anything that isn't a known
command and doesn't match an app just gets asked to the model, matching
how a Siri-like assistant behaves.

Single-turn only -- no conversation memory across follow-ups. See the
project plan for why: it would need a materially different interaction
model (no natural "end the conversation" phrase, listen_for_followup's
timeout would apply every turn, no barge-in), not just plumbing.
"""
import logging

import requests

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.registry.schema import Registry

_TIMEOUT_SECONDS = 30.0


def handle_converse(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    tts.say("Let me think.")  # CPU inference can take several seconds
    try:
        reply = _ask(target, config)
    except requests.exceptions.ConnectionError:
        log.warning("Ollama not reachable at %s", config.ollama.host)
        tts.say("I can't reach the local AI model right now.")
        return HandlerResult()
    except Exception:
        log.exception("Ollama request failed")
        tts.say("Something went wrong asking the AI model.")
        return HandlerResult()

    tts.say(reply)
    return HandlerResult()


def _ask(prompt: str, config: Config) -> str:
    response = requests.post(
        f"{config.ollama.host}/api/generate",
        json={
            "model": config.ollama.model,
            "prompt": prompt,
            "system": config.ollama.system_prompt,
            "stream": False,
        },
        timeout=_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json().get("response", "").strip() or "I don't have anything to say to that."
