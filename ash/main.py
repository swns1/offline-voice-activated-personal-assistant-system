"""Ash orchestrator.

Phase 5 milestone: wake-word triggered instead of a keypress. Saying
the configured keyword starts a VAD-gated recording, which is
transcribed and dispatched exactly as in Phase 3/4.
"""
from ash.actions.dispatcher import dispatch
from ash.audio.recorder import ContinuousListener
from ash.audio.stt import SpeechToText
from ash.audio.tts import TtsWorker
from ash.audio.wake_word import WakeWordDetector
from ash.config import load_config
from ash.registry.loader import load_registry
from ash.utils.bootstrap import check_wake_word_models
from ash.utils.logging_setup import setup_logging


def main() -> None:
    log = setup_logging()
    config = load_config()
    check_wake_word_models(config.wake_word.keyword)

    tts = TtsWorker()
    tts.start()

    print("Loading speech-to-text model...")
    stt = SpeechToText()
    registry = load_registry()
    log.info("Ash Phase 5 starting (%d app entries, %d intents)",
              len(registry.apps), len(registry.intents))

    wake_detector = WakeWordDetector(
        keyword=config.wake_word.keyword,
        threshold=config.wake_word.threshold,
    )
    listener = ContinuousListener(
        wake_detector,
        input_device=config.audio.input_device,
        silence_ms=config.audio.silence_ms,
        max_record_seconds=config.audio.max_record_seconds,
    )

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
                tts.say(result.question)
                followup_audio = listener.listen_for_followup(
                    timeout_seconds=6.0, on_state_change=on_state_change
                )
                if followup_audio is None:
                    tts.say("Never mind.")
                    break
                answer = stt.transcribe(followup_audio)
                print(f"  heard (follow-up): {answer!r}")
                log.info("Follow-up transcript: %r", answer)
                result = result.resume(answer)
    except KeyboardInterrupt:
        pass
    finally:
        wake_detector.delete()
        tts.stop()
        log.info("Ash Phase 5 stopped")


if __name__ == "__main__":
    main()
