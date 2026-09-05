import logging

from ash.audio.tts import TtsWorker
from ash.launchers.exe_launcher import ExeLauncher
from ash.launchers.uri_launcher import UriLauncher
from ash.nlu.matcher import match_app
from ash.registry.schema import Registry

_LAUNCHERS = [ExeLauncher(), UriLauncher()]


def handle_open(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger) -> None:
    result = match_app(target, registry)
    if result is None:
        log.info("No match for open target: %r", target)
        tts.say(f"I'm not sure what you mean by {target}.")
        return

    entry = result.entry
    launcher = next((l for l in _LAUNCHERS if l.can_handle(entry.launch)), None)
    if launcher is None:
        log.warning("No launcher handles entry %s (type %r)", entry.id, entry.launch.get("type"))
        tts.say(f"I don't know how to open {entry.id} yet.")
        return

    launcher.launch(entry.launch)
    log.info("Launched %s (matched %r, score %.0f)", entry.id, target, result.score)
    tts.say(f"Opening {entry.id.replace('_', ' ')}.")
