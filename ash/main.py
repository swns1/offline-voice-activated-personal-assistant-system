"""Ash's entry point: `python -m ash` opens the desktop window (if
PySide6 is installed and gui.enabled is on); `python -m ash --console`
runs voice-only in the terminal, as before the window existed.

Both modes share the same pieces, built by start_assistant(): one
AssistantCore (ash/core.py) that runs every command on a single worker
thread, and a VoiceLoop (ash/voice.py) feeding it from the microphone.
The window adds a second input (typing, buttons) to the same core.
"""
import argparse
import logging
import os
import sys
import threading
from collections.abc import Callable

from ash.actions.proactive import start as start_proactive_nudges
from ash.actions.timers import rehydrate as rehydrate_timers
from ash.audio.tts import TtsWorker
from ash.config import Config, load_config
from ash.core import HEARD, STATUS, AssistantCore, Event
from ash.privacy.egress import OfflineModeError
from ash.privacy.redact import set_log_content
from ash.registry.auto_build import refresh_registry_auto
from ash.registry.loader import load_registry
from ash.tray.icon import run_with_tray
from ash.utils.autostart import sync_autostart
from ash.utils.bootstrap import check_wake_word_models
from ash.utils.hotkey import register_mute_hotkey
from ash.utils.logging_setup import apply_log_retention, setup_logging
from ash.utils.ollama import MODEL_MISSING, READY, server_status
from ash.voice import VoiceLoop

OFFLINE_DOWNLOAD_MESSAGE = (
    "Ash needs to download its speech-recognition model once, but offline mode is on. "
    "Turn offline mode off to allow this one download (in the window's Privacy tab, or: "
    r'.venv\Scripts\python.exe -c "from ash.privacy import consent; consent.set_offline_mode(False)")'
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ash", description="Ash, an offline voice assistant")
    parser.add_argument("--console", action="store_true",
                        help="voice only, in this terminal (no desktop window)")
    parser.add_argument("--minimized", action="store_true",
                        help="start with the window hidden in the system tray")
    parser.add_argument("--selftest", action="store_true",
                        help="check every engine loads (no speaking, microphone or downloads), then exit")
    args = parser.parse_args(argv)
    _ensure_std_streams()

    if args.selftest:
        from ash.selftest import report, run_selftest

        text, passed = report(run_selftest(load_config()))
        print(text)
        sys.exit(0 if passed else 1)

    log = setup_logging()
    config = load_config()
    set_log_content(config.privacy.log_transcripts)
    deleted = apply_log_retention(config.privacy.log_retention_days, log)
    if deleted:
        log.info("Deleted %d log file(s) older than %d days", len(deleted), config.privacy.log_retention_days)
    try:
        sync_autostart(config.autostart)
    except Exception:
        log.exception("Failed to sync autostart registry setting")

    if config.gui.enabled and not args.console:
        try:
            from ash.gui.app import run_gui
        except ImportError:
            log.warning("PySide6 isn't installed; running voice-only")
            print("The desktop window needs PySide6 (pip install -r requirements.txt). Running voice-only.")
        else:
            # The window checks for the speech models itself, and offers to
            # download any that are missing.
            run_gui(config, log, minimized=args.minimized or config.gui.start_minimized)
            return

    check_wake_word_models(config.wake_word.keyword)
    if config.tray.enabled:
        run_with_tray(lambda: run_console(config, log), log)
    else:
        run_console(config, log)


def _ensure_std_streams() -> None:
    """Without a console (Ash.exe, or pythonw.exe at sign-in) there is no
    stdout/stderr, and any library that writes progress to them -- e.g.
    the speech model's download progress bar -- would crash. Send them
    nowhere instead; the log file has everything that matters."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # open for the life of the process
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def start_assistant(config: Config, log: logging.Logger,
                    on_event: Callable[[Event], None] | None = None) -> AssistantCore:
    """Everything except the microphone: voice output, the app list,
    the command worker, timers, reminders and the mute hotkey.
    `on_event` is subscribed before anything can speak (a timer that
    went off while Ash was closed announces itself right away)."""
    from ash.setup_models import piper_voice_path

    tts = TtsWorker(engine=config.voice.engine, piper_model=piper_voice_path(config.voice.piper_voice))
    tts.start()

    if config.registry.auto_rescan_on_startup:
        try:
            count = refresh_registry_auto()
            log.info("Rescanned Start Menu/Steam: %d auto-discovered entries", count)
        except Exception:
            log.exception("Auto-rescan of registry.auto.yaml failed; using existing file")

    registry = load_registry()
    log.info("Ash starting (%d app entries, %d intents)", len(registry.apps), len(registry.intents))
    if _report_local_ai(config, log):
        from ash.nlu.tools import warm_up

        threading.Thread(target=warm_up, args=(config,), name="ai-warm-up", daemon=True).start()

    core = AssistantCore(registry, tts, log, config)
    if on_event is not None:
        core.subscribe(on_event)
    core.start()

    if config.hotkey.toggle_mute:
        register_mute_hotkey(config.hotkey.toggle_mute, core.tts, log)
    rehydrate_timers(core.tts, log)
    start_proactive_nudges(config, core.tts, log)
    return core


def run_console(config: Config, log: logging.Logger) -> None:
    core = start_assistant(config, log, on_event=_print_event)

    print("Loading speech-to-text model...")
    try:
        voice = VoiceLoop.load(core, config, log)
    except OfflineModeError:
        print(OFFLINE_DOWNLOAD_MESSAGE)
        log.error(OFFLINE_DOWNLOAD_MESSAGE)
        core.tts.stop()
        return

    print(f"Listening for wake word {config.wake_word.keyword!r}. Ctrl+C to quit.")
    try:
        voice.run()
    except KeyboardInterrupt:
        pass
    finally:
        core.stop()
        core.tts.stop()
        log.info("Ash stopped")


def _print_event(event: Event) -> None:
    if event.kind == HEARD:
        print(f"  heard ({event.source}): {event.text!r}")
    elif event.kind == STATUS:
        print(f"  [{event.text}]")


def _report_local_ai(config: Config, log: logging.Logger) -> bool:
    """One line at startup saying whether the local-AI features are on,
    so "why doesn't it chat?" has an answer without digging into config."""
    setting = config.ollama.enabled
    if setting is False:
        message = "Local AI: off (ollama.enabled is false in config.yaml)"
    else:
        status = server_status(config, fresh=True)
        if status == READY:
            message = f"Local AI: on (Ollama running, model {config.ollama.model})"
        elif status == MODEL_MISSING:
            message = (f"Local AI: off -- Ollama is running but the {config.ollama.model} "
                       f"model isn't downloaded (run: ollama pull {config.ollama.model})")
        elif setting == "auto":
            message = "Local AI: off for now (Ollama not running -- it'll be picked up automatically once it is)"
        else:
            message = f"Local AI: ON in config, but Ollama isn't reachable at {config.ollama.host}"
    print(message)
    log.info(message)
    return setting is not False and status == READY


if __name__ == "__main__":
    main()
