import logging

from ash.actions.converse import handle_converse
from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.launchers.exe_launcher import ExeLauncher
from ash.launchers.uri_launcher import UriLauncher
from ash.nlu.context import remember_app
from ash.nlu.matcher import MatchResult, match_app, match_candidates
from ash.registry.schema import Registry

_LAUNCHERS = [ExeLauncher(), UriLauncher()]

# Two candidates this close in fuzzy score are treated as a genuine tie
# worth asking about, rather than silently picking the marginally-higher
# one.
_AMBIGUITY_MARGIN = 5.0


def handle_open(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    result = match_app(target, registry)
    if result is None:
        log.info("No match for open target: %r", target)
        if config.ollama.enabled:
            return handle_converse(target, registry, tts, log, config)
        tts.say(f"I'm not sure what you mean by {target}.")
        return HandlerResult()

    if result.score < 100.0:  # an exact name match is never ambiguous
        candidates = match_candidates(target, registry, limit=3)
        if len(candidates) > 1 and candidates[0].score - candidates[1].score <= _AMBIGUITY_MARGIN:
            return _ask_which_app(candidates, tts, log)

    return _launch_entry(result, target, tts, log)


def _launch_entry(result: MatchResult, target: str, tts: TtsWorker, log: logging.Logger) -> HandlerResult:
    entry = result.entry
    launcher = next((l for l in _LAUNCHERS if l.can_handle(entry.launch)), None)
    if launcher is None:
        log.warning("No launcher handles entry %s (type %r)", entry.id, entry.launch.get("type"))
        tts.say(f"I don't know how to open {entry.id} yet.")
        return HandlerResult()

    launcher.launch(entry.launch)
    log.info("Launched %s (matched %r, score %.0f)", entry.id, target, result.score)
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
            log.info("Follow-up %r didn't resolve to either candidate", answer)
            tts.say("Never mind.")
            return HandlerResult()
        return _launch_entry(chosen, answer, tts, log)

    return HandlerResult(done=False, question=question, resume=resume)
