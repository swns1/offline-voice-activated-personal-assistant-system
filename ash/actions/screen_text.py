"""Exact on-screen text via local OCR (Tesseract, through pytesseract) --
complements ash/actions/vision.py's screen_describe, which asks a
vision-language model for a prose description (looser, better for
"what's happening"/general questions). OCR is what "read my screen"
literally means: exact strings, error codes, numbers, read directly off
the pixels rather than paraphrased by a model.

Needs the Tesseract OCR *engine* installed separately (like Ollama --
see README), not just the pytesseract pip package, which is only a thin
wrapper around the tesseract executable. Runs fully offline/locally, no
config gate needed (no network call, no account) -- if the engine isn't
installed, the error path below says so instead of crashing.

Deliberately text-only, no mouse/keyboard automation: reading the
screen and acting on it (e.g. "click Save") are different features with
a different safety bar -- a later, separately-scoped decision, not
something this module does.
"""
import logging

import pytesseract
from PIL import ImageGrab

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.registry.schema import Registry

# Tesseract's per-word confidence is 0-100 (or -1 for non-text regions) --
# filters obvious noise (icons, stray pixels) without being so strict
# real but slightly blurry text gets dropped.
_MIN_CONFIDENCE = 40
# A full-desktop screenshot can OCR to a wall of text (every taskbar icon,
# every browser tab) that would make for a very long, useless TTS reply --
# cap what's actually spoken.
_MAX_SPOKEN_CHARS = 500


def _read_screen_text() -> str:
    image = ImageGrab.grab()
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    words = [
        word for word, conf in zip(data["text"], data["conf"])
        if word.strip() and float(conf) >= _MIN_CONFIDENCE
    ]
    return " ".join(words)


def handle_screen_read_text(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    tts.say("Let me read that.")
    try:
        text = _read_screen_text()
    except pytesseract.TesseractNotFoundError:
        log.warning("Tesseract OCR engine not installed")
        tts.say("Reading the screen needs the Tesseract OCR engine installed -- see the README.")
        return HandlerResult()
    except Exception:
        log.exception("Screen OCR failed")
        tts.say("I couldn't read the screen.")
        return HandlerResult()

    if not text:
        tts.say("I didn't find any readable text on your screen.")
        return HandlerResult()

    if len(text) > _MAX_SPOKEN_CHARS:
        text = text[:_MAX_SPOKEN_CHARS].rsplit(" ", 1)[0] + "... there's more text than I can read out fully."
    tts.say(text)
    return HandlerResult()
