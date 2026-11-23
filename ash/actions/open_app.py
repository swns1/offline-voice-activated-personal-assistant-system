"""Opens apps/games. Two entry points:

- handle_open: you said "open/launch/start/run/play X". Loose phrasing
  gets some benefit of the doubt, and a miss triggers one rescan of the
  Start Menu/Steam library in case X was installed since Ash started.
- handle_open_guess: no command verb was recognized, so the grammar
  guessed "open <whole utterance>". Only a close name match opens
  anything (see ash/nlu/matcher.py); otherwise the utterance goes to the
  local AI as conversation, or gets "I'm not sure what you mean". No
  rescan here: most such utterances aren't app names at all, and a
  rescan costs a second and a file write each time.
"""
import logging

from ash.actions.converse import handle_converse
from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.launchers.exe_launcher import ExeLauncher
from ash.launchers.uri_launcher import UriLauncher
from ash.nlu.context import remember_app
from ash.nlu.matcher import MatchResult, match_app, match_candidates
from ash.privacy.redact import said
from ash.registry.auto_build import refresh_registry_auto
from ash.registry.loader import load_registry
from ash.registry.schema import Registry
from ash.utils.ollama import ai_enabled

_LAUNCHERS = [ExeLauncher(), UriLauncher()]

# Two candidates this close in fuzzy score are treated as a genuine tie
# worth asking about, rather than silently picking the marginally-higher
# one.
_AMBIGUITY_MARGIN = 5.0


def handle_open(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    return _open(target, registry, tts, log, config, guessed=False)


def handle_open_guess(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    return _open(target, registry, tts, log, config, guessed=True)


def _open(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config,
          *, guessed: bool) -> HandlerResult:
    result = match_app(target, registry, guessed=guessed)
    if result is None and not guessed:
        result = _retry_after_rescan(target, registry, log)
    if result is None:
        log.info("No match for %s target: %s", "guessed open" if guessed else "open", said(target))
        if ai_enabled(config):
            return handle_converse(target, registry, tts, log, config)
        tts.say(f"I'm not sure what you mean by {target}.")
        return HandlerResult()

    if result.score < 100.0:  # an exact name match is never ambiguous
        candidates = match_candidates(target, registry, limit=3, guessed=guessed)
        if len(candidates) > 1 and candidates[0].score - candidates[1].score <= _AMBIGUITY_MARGIN:
            return _ask_which_app(candidates, tts, log)

    return _launch_entry(result, target, tts, log)


def _retry_after_rescan(target: str, registry: Registry, log: logging.Logger) -> MatchResult | None:
    """No match on the first try -- it may be a game/app installed since
    Ash last started (the Start Menu/Steam scan only runs at startup by
    default, see RegistryConfig.auto_rescan_on_startup). Rescan once and
    retry before giving up, so a freshly-downloaded Steam game is
    voice-launchable without restarting Ash. Updates `registry.apps` in
    place so the rest of this session benefits too, not just this call.
    """
    try:
        refresh_registry_auto()
        fresh = load_registry()
    except Exception:
        log.exception("Rescan-on-miss failed for open target %s", said(target))
        return None
    registry.apps = fresh.apps
    result = match_app(target, registry)
    if result is not None:
        log.info("Rescan-on-miss found %r for target %s", result.entry.id, said(target))
    return result


def _launch_entry(result: MatchResult, target: str, tts: TtsWorker, log: logging.Logger) -> HandlerResult:
    entry = result.entry
    launcher = next((launcher for launcher in _LAUNCHERS if launcher.can_handle(entry.launch)), None)
    if launcher is None:
        log.warning("No launcher handles entry %s (type %r)", entry.id, entry.launch.get("type"))
        tts.say(f"I don't know how to open {entry.id} yet.")
        return HandlerResult()

    launcher.launch(entry.launch)
    log.info("Launched %s (matched %s, score %.0f)", entry.id, said(target), result.score)
    remember_app(entry.id.replace("_", " "))
    tts.say(f"Opening {entry.id.replace('_', ' ')}.")
    return HandlerResult()


def _ask_which_app(candidates: list[MatchResult], tts: TtsWorker, log: logging.Logger) -> HandlerResult:
    top_two = candidates[:2]
    spoken_names = [c.entry.id.replace("_", " ") for c in top_two]
    question = f"Did you mean {spoken_names[0]} or {spoken_names[1]}?"
    narrowed = Registry(apps=[c.entry for c in top_two])

    def resume(answer: str) -> HandlerResult:
        chosen = match_app(answer, narrowed)
        if chosen is None:
            log.info("Follow-up %s didn't resolve to either candidate", said(answer))
            tts.say("Never mind.")
            return HandlerResult()
        return _launch_entry(chosen, answer, tts, log)

    return HandlerResult(done=False, question=question, resume=resume)
