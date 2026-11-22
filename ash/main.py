"""Ash orchestrator: wake word -> VAD-gated recording -> speech-to-text
-> dispatch, then any follow-up questions (clarifications,
confirmations) the handler asks.

_run_assistant() is the actual listening loop, split out from main()
so it can run on a background thread when the tray icon is enabled --
pystray's Windows backend needs to own the calling thread's message
loop (see ash/tray/icon.py).
"""
import logging

from ash.actions.dispatcher import dispatch
from ash.actions.proactive import start as start_proactive_nudges
from ash.actions.results import HandlerResult
from ash.actions.timers import rehydrate as rehydrate_timers
from ash.audio.recorder import ContinuousListener
from ash.audio.stt import SpeechToText
from ash.audio.tts import TtsWorker
from ash.audio.wake_word import WakeWordDetector
from ash.config import Config, load_config
from ash.registry.auto_build import refresh_registry_auto
from ash.registry.loader import load_registry
from ash.security import voice_gate
from ash.tray.icon import run_with_tray
from ash.utils.autostart import sync_autostart
from ash.utils.bootstrap import check_wake_word_models
from ash.utils.hotkey import register_mute_hotkey
from ash.utils.logging_setup import setup_logging
from ash.utils.ollama import MODEL_MISSING, READY, server_status


def main() -> None:
    log = setup_logging()
    config = load_config()
    check_wake_word_models(config.wake_word.keyword)

    try:
        sync_autostart(config.autostart)
    except Exception:
        log.exception("Failed to sync autostart registry setting")

    if config.tray.enabled:
        run_with_tray(lambda: _run_assistant(config, log), log)
    else:
        _run_assistant(config, log)


def _run_assistant(config: Config, log: logging.Logger) -> None:
    tts = TtsWorker()
    tts.start()

    if config.registry.auto_rescan_on_startup:
        try:
            count = refresh_registry_auto()
            log.info("Rescanned Start Menu/Steam: %d auto-discovered entries", count)
        except Exception:
            log.exception("Auto-rescan of registry.auto.yaml failed; using existing file")

    print("Loading speech-to-text model...")
    stt = SpeechToText()
    registry = load_registry()
    log.info("Ash starting (%d app entries, %d intents)",
              len(registry.apps), len(registry.intents))
    _report_local_ai(config, log)

    wake_detector = WakeWordDetector(
        keyword=config.wake_word.keyword,
        threshold=config.wake_word.threshold,
    )
    listener = ContinuousListener(
        wake_detector,
        input_device=config.audio.input_device,
        silence_ms=config.audio.silence_ms,
        max_record_seconds=config.audio.max_record_seconds,
        is_speaking=tts.is_speaking if config.audio.barge_in_enabled else None,
        on_barge_in=tts.stop_speaking if config.audio.barge_in_enabled else None,
    )

    if config.hotkey.toggle_mute:
        register_mute_hotkey(config.hotkey.toggle_mute, tts, log)

    rehydrate_timers(tts, log)
    start_proactive_nudges(config, tts, log)
    tts.say("Ash is listening.")
    print(f"Listening for wake word {config.wake_word.keyword!r}. Ctrl+C to quit.")

    def on_state_change(state: str) -> None:
        print(f"  [{state}]")

    try:
        for utterance in listener.listen(on_state_change=on_state_change):
            text = stt.transcribe(utterance)
            print(f"  heard: {text!r}")
            log.info("Transcript: %r", text)
            result = dispatch(text, registry, tts, log, config)

            while not result.done:
                if result.question:  # None for a conversational continuation --
                    tts.say(result.question)  # the reply just spoken is prompt enough
                followup_audio = listener.listen_for_followup(
                    timeout_seconds=6.0, on_state_change=on_state_change
                )
                if followup_audio is None:
                    tts.say("Never mind.")
                    break
                answer = stt.transcribe(followup_audio)
                print(f"  heard (follow-up): {answer!r}")
                log.info("Follow-up transcript: %r", answer)
                if result.requires_voice_match and not voice_gate.verify(followup_audio, config, log):
                    log.warning("Voice gate blocked a confirmation answer")
                    tts.say("That didn't sound like you, so I'm not doing that.")
                    result = HandlerResult()
                else:
                    result = result.resume(answer)
    except KeyboardInterrupt:
        pass
    finally:
        wake_detector.delete()
        tts.stop()
        log.info("Ash stopped")


def _report_local_ai(config: Config, log: logging.Logger) -> None:
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


if __name__ == "__main__":
    main()
