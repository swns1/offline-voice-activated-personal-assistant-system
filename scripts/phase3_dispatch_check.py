import logging
from ash.actions.dispatcher import dispatch
from ash.audio.tts import TtsWorker
from ash.config import load_config
from ash.registry.loader import load_registry

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("test")

class FakeTts:
    def say(self, text):
        print(f"[TTS] {text}")

registry = load_registry()
config = load_config()
tts = FakeTts()

for phrase in ["open notepad", "what is ubiquitous", "open steam", "open some totally unknown app xyz"]:
    print(f"\n--- {phrase!r} ---")
    dispatch(phrase, registry, tts, log, config)
