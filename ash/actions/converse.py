"""Fallback conversational "brain" via a local Ollama server -- reached
only from ash/actions/open_app.py's no-match branch (gated on
ash.utils.ollama.ai_enabled), not through its own grammar verb or dispatcher
entry. No special trigger phrase needed: anything that isn't a known
command and doesn't match an app just gets asked to the model, matching
how a Siri-like assistant behaves.

Carries a short rolling message history across follow-ups (via
Ollama's /api/chat instead of the earlier single-shot /api/generate),
chained through HandlerResult.resume() the same way every other
multi-turn flow in this codebase works -- so "what's the capital of
France" -> "what's its population" resolves "its" correctly. Bounded to
_MAX_MESSAGES so a long-running chat doesn't grow the prompt forever,
and ends immediately (without asking the model) if the user says
"stop"/"cancel" instead of continuing the conversation.

Also folds in ash/actions/memory.py's durable facts ("remember I'm
vegetarian") via facts_context() -- that's persisted storage separate
from this module's own in-conversation history, so it survives past
this one conversation and past restarts.
"""
import logging

from ash.actions.memory import facts_context
from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.nlu.grammar import parse
from ash.privacy import egress
from ash.registry.schema import Registry
from ash.utils.ollama import chat

_TIMEOUT_SECONDS = 30.0
_MAX_MESSAGES = 20  # ~10 exchanges -- keeps the prompt bounded and gives a long chat a natural end


def handle_converse(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    return _ask_and_continue([{"role": "user", "content": target}], tts, log, config)


def _ask_and_continue(messages: list[dict], tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    tts.say("Let me think.")  # CPU inference can take several seconds
    try:
        reply = _ask(messages, config)
    except egress.NetworkUnreachable:
        log.warning("Ollama not reachable at %s", config.ollama.host)
        tts.say("I can't reach the local AI model right now.")
        return HandlerResult()
    except Exception:
        log.exception("Ollama request failed")
        tts.say("Something went wrong asking the AI model.")
        return HandlerResult()

    tts.say(reply)
    messages = messages + [{"role": "assistant", "content": reply}]

    if len(messages) >= _MAX_MESSAGES:
        log.info("Conversation reached %d messages, ending without offering a follow-up", len(messages))
        return HandlerResult()

    def resume(answer: str) -> HandlerResult:
        if parse(answer).intent == "stop":
            tts.say("OK.")
            return HandlerResult()
        return _ask_and_continue(messages + [{"role": "user", "content": answer}], tts, log, config)

    # question=None: the reply above already spoken is the "prompt" for
    # whatever comes next -- main.py's loop only speaks result.question
    # when it's set, so this just keeps listening without repeating
    # anything.
    return HandlerResult(done=False, question=None, resume=resume)


def _ask(messages: list[dict], config: Config) -> str:
    system_prompt = config.ollama.system_prompt + facts_context()
    content = (chat(config, messages, system=system_prompt, timeout=_TIMEOUT_SECONDS).get("content") or "").strip()
    return content or "I don't have anything to say to that."
