"""Voice commands for your privacy settings:

- "go offline" / "go online": offline mode blocks everything that would
  leave this PC (ash/privacy/egress.py), whatever you've allowed.
- "allow web search" / "stop allowing Spotify": give or withdraw
  permission for one online feature (ash/privacy/consent.py).
- "what have you sent online": a summary of the network log
  (ash/privacy/network_log.py) -- what went where, never the content.
"""
import logging

from rapidfuzz import fuzz, process, utils

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.privacy import consent, network_log
from ash.privacy.egress import FEATURES, OnlineFeature
from ash.registry.schema import Registry

_FEATURE_MATCH_CUTOFF = 75.0


def handle_offline_on(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    consent.set_offline_mode(True)
    log.info("Offline mode on")
    tts.say("Offline mode is on. Nothing will leave this PC until you say 'go online'.")
    return HandlerResult()


def handle_offline_off(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    consent.set_offline_mode(False)
    log.info("Offline mode off")
    tts.say("Offline mode is off. Online features you've allowed can be used again.")
    return HandlerResult()


def handle_allow(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    feature = _resolve_feature(target, tts)
    if feature is None:
        return HandlerResult()
    if feature.consent_by_config:
        tts.say(f"{feature.name.capitalize()} {feature.fixed_reason}, so it isn't switched on or off by voice.")
        return HandlerResult()
    consent.grant(feature.key)
    log.info("You allowed %s", feature.key)
    reply = f"Okay, {feature.name} is allowed. It sends {feature.sends} to {feature.service}."
    if consent.offline_mode():
        reply += " Offline mode is still on, though -- say 'go online' to use it."
    tts.say(reply)
    return HandlerResult()


def handle_disallow(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    feature = _resolve_feature(target, tts)
    if feature is None:
        return HandlerResult()
    if feature.consent_by_config:
        tts.say(f"{feature.name.capitalize()} {feature.fixed_reason}, so it isn't switched on or off by voice.")
        return HandlerResult()
    consent.deny(feature.key)
    log.info("You withdrew permission for %s", feature.key)
    tts.say(f"Okay, I'll stop using {feature.service} for {feature.name}.")
    return HandlerResult()


def handle_network_activity(
    target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config,
) -> HandlerResult:
    summary = network_log.summary(days=7)
    if consent.offline_mode():
        summary += " Offline mode is on right now."
    tts.say(summary)
    return HandlerResult()


def _resolve_feature(target: str, tts: TtsWorker) -> OnlineFeature | None:
    """Match "web search" / "duckduckgo" / "spotify" to an online feature."""
    aliases: dict[str, OnlineFeature] = {}
    for feature in FEATURES.values():
        for alias in (feature.name, feature.key.replace("_", " "), feature.service):
            aliases[alias.lower()] = feature

    target = target.strip().lower()
    best = process.extractOne(target, aliases.keys(), scorer=fuzz.WRatio,
                              processor=utils.default_process, score_cutoff=_FEATURE_MATCH_CUTOFF) if target else None
    if best is None:
        choices = ", ".join(f.name for f in FEATURES.values() if not f.consent_by_config)
        tts.say(f"I don't have an online feature called {target or 'that'}. The ones I can change are: {choices}.")
        return None
    return aliases[best[0]]
