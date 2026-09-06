"""Screen understanding via a local Ollama vision model ("what's on my
screen", "what does this error say") -- reuses the Ollama infrastructure
already built for converse.py, gated behind the same config.ollama.enabled,
but a separate model pull (config.ollama.vision_model) since llama3.2
itself is text-only.

Captures a screenshot, resizes and re-compresses it before sending: a
raw 1920x1080 PNG is ~2-3MB (~3MB again as base64) -- a resized JPEG at
_MAX_WIDTH is a couple hundred KB at most, a big difference in request
latency for no real loss in what a vision model needs to read text or
describe layout (confirmed empirically: a real screenshot went from
~3.1M base64 chars to ~20K after resizing to 1280px wide + JPEG q80).
"""
import base64
import io
import logging

import requests
from PIL import ImageGrab

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.registry.schema import Registry

_TIMEOUT_SECONDS = 60.0  # vision inference is slower than text-only
_MAX_WIDTH = 1280
_JPEG_QUALITY = 80
_DEFAULT_QUESTION = "Describe what's on this screen concisely, in 1-3 sentences."


def _capture_screenshot_base64() -> str:
    image = ImageGrab.grab()
    if image.width > _MAX_WIDTH:
        ratio = _MAX_WIDTH / image.width
        image = image.resize((_MAX_WIDTH, round(image.height * ratio)))
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=_JPEG_QUALITY)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def handle_screen_describe(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    if not config.ollama.enabled:
        tts.say("Screen understanding needs Ollama enabled.")
        return HandlerResult()

    tts.say("Let me look.")
    try:
        image_b64 = _capture_screenshot_base64()
    except Exception:
        log.exception("Failed to capture screenshot")
        tts.say("I couldn't capture the screen.")
        return HandlerResult()

    question = target.strip() or _DEFAULT_QUESTION
    try:
        answer = _ask_vision(question, image_b64, config)
    except requests.exceptions.ConnectionError:
        log.warning("Ollama not reachable at %s", config.ollama.host)
        tts.say("I can't reach the local AI model right now.")
        return HandlerResult()
    except Exception:
        log.exception("Ollama vision request failed")
        tts.say("Something went wrong looking at the screen.")
        return HandlerResult()

    tts.say(answer)
    return HandlerResult()


def _ask_vision(question: str, image_b64: str, config: Config) -> str:
    response = requests.post(
        f"{config.ollama.host}/api/chat",
        json={
            "model": config.ollama.vision_model,
            "messages": [{"role": "user", "content": question, "images": [image_b64]}],
            "stream": False,
        },
        timeout=_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    content = response.json().get("message", {}).get("content", "").strip()
    return content or "I don't have anything to say about that."
