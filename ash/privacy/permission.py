"""Asking for permission to use online features -- normally once, at
startup, the way a phone asks its privacy questions during setup rather
than in the middle of using it.

startup_questions(): when Ash starts, it asks about each online feature
that's switched on and that you haven't answered yet (all of them on
first run; just the new one when a later version adds a feature, or
when you set up Spotify). For each it says what would be sent, to whom,
and why. Your answers are remembered; nothing is asked again unless you
delete your data.

ask_permission_if_needed(): the backstop at the moment of use. Online
handlers start with:

    blocked = ask_permission_if_needed(WEB_SEARCH.key, retry=lambda: handle_search(...), ...)
    if blocked is not None:
        return blocked

- Offline mode on: says so, and how to turn it off.
- Already allowed: returns None and the handler carries on.
- You said no before: says so, and how to change it -- no nagging.
- Never answered (you didn't reply at startup): asks the same question
  then, and runs the command straight away on "yes".

Either way, nothing is sent until you've said yes.
"""
import logging
from collections.abc import Callable

from ash.actions.confirmation import is_affirmative
from ash.actions.results import YES_NO, HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.privacy import consent
from ash.privacy.egress import FEATURES, OnlineFeature

HOW_TO_CHANGE = "You can change these any time by saying 'allow' or 'stop allowing', and the feature's name."


def consent_question(feature: OnlineFeature) -> str:
    return (f"To {feature.purpose}, I'd send {feature.sends} to {feature.service}, "
            f"over the internet. Is that okay?")


def _record_answer(feature: OnlineFeature, answer: str, log: logging.Logger) -> bool:
    allowed = is_affirmative(answer)
    (consent.grant if allowed else consent.deny)(feature.key)
    log.info("You %s %s", "allowed" if allowed else "did not allow", feature.key)
    return allowed


# --- at startup ------------------------------------------------------------------

def unanswered_features(config: Config) -> list[OnlineFeature]:
    return [
        f for f in FEATURES.values()
        if not f.consent_by_config and f.in_use(config) and consent.status(f.key) == consent.UNASKED
    ]


def startup_questions(config: Config, tts: TtsWorker, log: logging.Logger) -> HandlerResult:
    """Speaks a short introduction and returns the first question (or a
    done result if there's nothing to ask). ash/main.py runs the answers
    through its usual follow-up loop."""
    pending = unanswered_features(config)
    if not pending or consent.offline_mode():
        return HandlerResult()  # offline mode: nothing would be sent anyway; ask once you're back online

    if not consent.all_consents():
        tts.say("Before we start, a quick privacy check. Everything I do stays on this PC, "
                "except a few features that need the internet. I'll ask about each one once.")
    elif len(pending) == 1:
        tts.say("One quick privacy question about a feature that needs the internet.")
    else:
        tts.say("A few quick privacy questions about features that need the internet.")
    return _ask(pending, 0, tts, log)


def _ask(pending: list[OnlineFeature], index: int, tts: TtsWorker, log: logging.Logger) -> HandlerResult:
    feature = pending[index]

    def resume(answer: str) -> HandlerResult:
        allowed = _record_answer(feature, answer, log)
        tts.say(f"Okay, {feature.name} is on." if allowed else f"Okay, I won't use {feature.service}.")
        if index + 1 < len(pending):
            return _ask(pending, index + 1, tts, log)
        tts.say(f"That's all. {HOW_TO_CHANGE}")
        return HandlerResult()

    return HandlerResult(
        done=False, question=consent_question(feature), resume=resume,
        timeout_reply="I'll ask again later. Nothing is sent until you say yes.", choices=YES_NO,
    )


# --- at the moment of use (backstop) ---------------------------------------------------

def ask_permission_if_needed(
    feature_key: str, retry: Callable[[], HandlerResult | None], *,
    tts: TtsWorker, log: logging.Logger,
) -> HandlerResult | None:
    feature = FEATURES[feature_key]

    if consent.offline_mode():
        log.info("Blocked %s: offline mode", feature_key)
        tts.say(f"I'm in offline mode, so I can't use {feature.name} right now. "
                f"Say 'go online' to allow it again.")
        return HandlerResult()

    if feature.consent_by_config:
        return None

    current = consent.status(feature_key)
    if current == consent.GRANTED:
        return None
    if current == consent.DENIED:
        log.info("Blocked %s: you chose not to allow it", feature_key)
        tts.say(f"You chose not to allow {feature.name}, which would send {feature.sends} "
                f"to {feature.service}. Say 'allow {feature.name}' if you change your mind.")
        return HandlerResult()

    def resume(answer: str) -> HandlerResult:
        if _record_answer(feature, answer, log):
            result = retry()
            return result if result is not None else HandlerResult()
        tts.say(f"Okay, I won't use {feature.service}. Say 'allow {feature.name}' if you change your mind.")
        return HandlerResult()

    return HandlerResult(
        done=False,
        question=consent_question(feature) + " I'll remember your answer, and you can change it any time.",
        resume=resume, choices=YES_NO,
    )
