"""Asks for permission before an online feature is used, so the
backstop checks in ash/privacy/egress.py never have to fire.

Online handlers start with:

    blocked = ask_permission_if_needed(WEB_SEARCH.key, retry=lambda: handle_search(...), ...)
    if blocked is not None:
        return blocked

- Offline mode on: says so, and how to turn it off.
- Already allowed: returns None and the handler carries on.
- You said no before: says so, and how to change it -- no nagging.
- Never asked: explains what would be sent, to whom, over the
  internet, and asks. "Yes" is remembered and the original command runs
  straight away (`retry`); anything else is remembered as no.
"""
import logging
from typing import Callable

from ash.actions.confirmation import is_affirmative
from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.privacy import consent
from ash.privacy.egress import FEATURES


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

    question = (f"To {feature.purpose}, I'd send {feature.sends} to {feature.service}, over the "
                f"internet. Is that okay? I'll remember your answer, and you can change it any time.")

    def resume(answer: str) -> HandlerResult:
        if is_affirmative(answer):
            consent.grant(feature_key)
            log.info("You allowed %s", feature_key)
            result = retry()
            return result if result is not None else HandlerResult()
        consent.deny(feature_key)
        log.info("You did not allow %s", feature_key)
        tts.say(f"Okay, I won't use {feature.service}. Say 'allow {feature.name}' if you change your mind.")
        return HandlerResult()

    return HandlerResult(done=False, question=question, resume=resume)
