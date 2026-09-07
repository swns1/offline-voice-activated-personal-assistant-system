import logging

from ash.actions import screen_text
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


def test_reads_screen_text_aloud(monkeypatch):
    monkeypatch.setattr(screen_text, "_read_screen_text", lambda: "Error 404: page not found")
    tts = FakeTts()

    result = screen_text.handle_screen_read_text("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.said == ["Let me read that.", "Error 404: page not found"]


def test_no_readable_text_says_so(monkeypatch):
    monkeypatch.setattr(screen_text, "_read_screen_text", lambda: "")
    tts = FakeTts()

    screen_text.handle_screen_read_text("", Registry(), tts, log, Config())

    assert tts.said[-1] == "I didn't find any readable text on your screen."


def test_long_text_is_truncated_with_a_caveat(monkeypatch):
    long_text = "word " * 200  # well over _MAX_SPOKEN_CHARS
    monkeypatch.setattr(screen_text, "_read_screen_text", lambda: long_text)
    tts = FakeTts()

    screen_text.handle_screen_read_text("", Registry(), tts, log, Config())

    spoken = tts.said[-1]
    assert len(spoken) < len(long_text)
    assert "there's more text" in spoken


def test_tesseract_not_installed_gives_a_helpful_message(monkeypatch):
    def boom():
        raise screen_text.pytesseract.TesseractNotFoundError()
    monkeypatch.setattr(screen_text, "_read_screen_text", boom)
    tts = FakeTts()

    screen_text.handle_screen_read_text("", Registry(), tts, log, Config())

    assert "Tesseract" in tts.said[-1]


def test_other_exception_gives_a_generic_message(monkeypatch):
    def boom():
        raise RuntimeError("capture failed")
    monkeypatch.setattr(screen_text, "_read_screen_text", boom)
    tts = FakeTts()

    screen_text.handle_screen_read_text("", Registry(), tts, log, Config())

    assert tts.said[-1] == "I couldn't read the screen."


def test_read_screen_text_filters_low_confidence_words(monkeypatch):
    fake_data = {
        "text": ["Hello", "", "garbled", "World"],
        "conf": [95, 50, 10, 88],
    }
    monkeypatch.setattr(screen_text.ImageGrab, "grab", lambda: object())
    monkeypatch.setattr(screen_text.pytesseract, "image_to_data", lambda image, output_type: fake_data)

    text = screen_text._read_screen_text()

    assert text == "Hello World"
