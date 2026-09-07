"""Guided desktop actions: click/type based on exact on-screen text
locations, via the same Tesseract OCR ash/actions/screen_text.py
already uses -- Ash's version of the "computer use" pattern (Anthropic
Computer Use, OpenAI Operator, Microsoft Copilot Actions). Targets by
VISIBLE TEXT LABEL, not AI-guessed pixel coordinates: local
vision-language models are notoriously imprecise at pixel-level
grounding, while OCR word/line bounding boxes are exact. This means it
can only click/type into things with visible text (a labeled button, a
menu item) -- it can't target a bare icon. Intentional v1 scope limit,
not an oversight.

This is the one feature in Ash that directly manipulates the desktop,
so it's gated more strictly than anything else in this codebase:
- off by default (config.desktop_control.enabled)
- every action still asks for a spoken confirmation naming exactly
  what it found (dynamic, like ash/actions/calendar.py's
  handle_calendar_add -- the question depends on what was located, not
  a fixed string)
- reuses ash/security/voice_gate.py's voice-match check on that
  confirmation too when config.security.voice_gate_enabled -- the same
  requires_voice_match flag ash/actions/confirmation.py's
  wrap_with_confirmation() sets, so ash/main.py's existing gate check
  covers this with no new plumbing

pyautogui.FAILSAFE stays on (the library's default): dragging the mouse
to a screen corner aborts any in-progress pyautogui action.

Known limitations, not fully verifiable in this environment:
- ImageGrab.grab()'s pixel coordinates and pyautogui's click
  coordinates could disagree under Windows display scaling
  (125%/150%) -- see README.
- If two on-screen elements share the exact same label, only one
  candidate is kept (the later one, by simple dict overwrite) -- no
  disambiguation prompt for this yet, unlike ash/actions/open_app.py's
  ambiguous-app handling.
"""
import logging

import pyautogui
import pytesseract
from PIL import ImageGrab
from rapidfuzz import fuzz, process

from ash.actions.confirmation import AFFIRMATIVE_ANSWERS
from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.registry.schema import Registry

_MIN_CONFIDENCE = 40  # same OCR-noise filter as ash/actions/screen_text.py
_FUZZY_SCORE_CUTOFF = 70.0


def _ocr_words() -> list[dict]:
    image = ImageGrab.grab()
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    words = []
    for i, text in enumerate(data["text"]):
        if not text.strip() or float(data["conf"][i]) < _MIN_CONFIDENCE:
            continue
        words.append({
            "text": text, "left": data["left"][i], "top": data["top"][i],
            "width": data["width"][i], "height": data["height"][i],
            "line_key": (data["block_num"][i], data["par_num"][i], data["line_num"][i]),
        })
    return words


def _candidates(words: list[dict]) -> dict[str, tuple[int, int]]:
    """Maps every candidate label -- each individual word AND each whole
    reconstructed line (for multi-word labels like "OK button") -- to
    its center point."""
    candidates: dict[str, tuple[int, int]] = {}
    for word in words:
        cx = word["left"] + word["width"] // 2
        cy = word["top"] + word["height"] // 2
        candidates[word["text"]] = (cx, cy)

    lines: dict[tuple, list[dict]] = {}
    for word in words:
        lines.setdefault(word["line_key"], []).append(word)
    for line_words in lines.values():
        text = " ".join(w["text"] for w in line_words)
        left = min(w["left"] for w in line_words)
        top = min(w["top"] for w in line_words)
        right = max(w["left"] + w["width"] for w in line_words)
        bottom = max(w["top"] + w["height"] for w in line_words)
        candidates[text] = ((left + right) // 2, (top + bottom) // 2)

    return candidates


def _find_label(label: str) -> tuple[int, int, str] | None:
    candidates = _candidates(_ocr_words())
    if not candidates:
        return None
    best = process.extractOne(label, candidates.keys(), scorer=fuzz.WRatio, score_cutoff=_FUZZY_SCORE_CUTOFF)
    if best is None:
        return None
    matched_text = best[0]
    x, y = candidates[matched_text]
    return x, y, matched_text


def handle_screen_click(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    if not config.desktop_control.enabled:
        tts.say("Desktop control isn't turned on.")
        return HandlerResult()

    label = target.strip()
    if not label:
        tts.say("Click what?")
        return HandlerResult()

    try:
        found = _find_label(label)
    except pytesseract.TesseractNotFoundError:
        log.warning("Tesseract OCR engine not installed")
        tts.say("Reading the screen needs the Tesseract OCR engine installed -- see the README.")
        return HandlerResult()
    except Exception:
        log.exception("Screen OCR failed while looking for %r", label)
        tts.say("I couldn't read the screen.")
        return HandlerResult()

    if found is None:
        tts.say(f"I couldn't find {label} on your screen.")
        return HandlerResult()

    x, y, matched_text = found

    def resume(answer: str) -> HandlerResult:
        if answer.strip().lower() not in AFFIRMATIVE_ANSWERS:
            log.info("Screen click declined: %r", answer)
            tts.say("Never mind.")
            return HandlerResult()
        try:
            pyautogui.click(x, y)
        except Exception:
            log.exception("pyautogui click failed at (%d, %d)", x, y)
            tts.say("I couldn't click that.")
            return HandlerResult()
        log.info("Clicked %r at (%d, %d)", matched_text, x, y)
        tts.say(f"Clicked {matched_text}.")
        return HandlerResult()

    return HandlerResult(
        done=False, question=f"Click '{matched_text}'?", resume=resume,
        requires_voice_match=config.security.voice_gate_enabled,
    )


def handle_screen_type(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    if not config.desktop_control.enabled:
        tts.say("Desktop control isn't turned on.")
        return HandlerResult()

    text = target.strip()
    if not text:
        tts.say("Type what?")
        return HandlerResult()

    def resume(answer: str) -> HandlerResult:
        if answer.strip().lower() not in AFFIRMATIVE_ANSWERS:
            log.info("Screen type declined: %r", answer)
            tts.say("Never mind.")
            return HandlerResult()
        try:
            pyautogui.write(text)
        except Exception:
            log.exception("pyautogui write failed")
            tts.say("I couldn't type that.")
            return HandlerResult()
        log.info("Typed %r", text)
        tts.say("Done.")
        return HandlerResult()

    return HandlerResult(
        done=False, question=f"Type '{text}'?", resume=resume,
        requires_voice_match=config.security.voice_gate_enabled,
    )
