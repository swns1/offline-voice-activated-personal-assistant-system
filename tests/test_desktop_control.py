import logging

from ash.actions import desktop_control
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


def _enabled_config(**overrides) -> Config:
    config = Config()
    config.desktop_control.enabled = True
    for key, value in overrides.items():
        setattr(config.security, key, value)
    return config


def _mock_ocr(monkeypatch, words: list[dict]):
    """words: list of {"text", "left", "top", "width", "height", "conf"}"""
    data = {
        "text": [w["text"] for w in words],
        "left": [w["left"] for w in words],
        "top": [w["top"] for w in words],
        "width": [w["width"] for w in words],
        "height": [w["height"] for w in words],
        "conf": [w.get("conf", 95) for w in words],
        "block_num": [w.get("block_num", 1) for w in words],
        "par_num": [w.get("par_num", 1) for w in words],
        "line_num": [w.get("line_num", i) for i, w in enumerate(words)],
    }
    monkeypatch.setattr(desktop_control.ImageGrab, "grab", lambda: object())
    monkeypatch.setattr(desktop_control.pytesseract, "image_to_data", lambda image, output_type: data)


# --- feature disabled ---

def test_disabled_click_says_so_and_never_touches_ocr(monkeypatch):
    calls = []
    monkeypatch.setattr(desktop_control, "_find_label", lambda label: calls.append(label) or None)
    tts = FakeTts()

    result = desktop_control.handle_screen_click("save", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.said == ["Desktop control isn't turned on."]
    assert calls == []


def test_disabled_type_says_so(monkeypatch):
    tts = FakeTts()

    result = desktop_control.handle_screen_type("hello", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.said == ["Desktop control isn't turned on."]


# --- click ---

def test_click_empty_target_asks_what(monkeypatch):
    tts = FakeTts()

    result = desktop_control.handle_screen_click("", Registry(), tts, log, _enabled_config())

    assert result == HandlerResult()
    assert tts.said == ["Click what?"]


def test_click_label_not_found_says_so(monkeypatch):
    _mock_ocr(monkeypatch, [{"text": "Cancel", "left": 0, "top": 0, "width": 50, "height": 20}])
    tts = FakeTts()

    result = desktop_control.handle_screen_click("save", Registry(), tts, log, _enabled_config())

    assert result == HandlerResult()
    assert "couldn't find save" in tts.said[-1]


def test_click_found_asks_confirmation_then_clicks(monkeypatch):
    _mock_ocr(monkeypatch, [{"text": "Save", "left": 100, "top": 200, "width": 40, "height": 20}])
    clicked = []
    monkeypatch.setattr(desktop_control.pyautogui, "click", lambda x, y: clicked.append((x, y)))
    tts = FakeTts()

    result = desktop_control.handle_screen_click("save", Registry(), tts, log, _enabled_config())

    assert result.done is False
    assert result.question == "Click 'Save'?"
    assert clicked == []  # not yet -- needs confirmation first

    final = result.resume("yes")

    assert final == HandlerResult()
    assert clicked == [(120, 210)]  # center of the 40x20 box at (100, 200)
    assert "Clicked Save" in tts.said[-1]


def test_click_declined_never_clicks(monkeypatch):
    _mock_ocr(monkeypatch, [{"text": "Save", "left": 100, "top": 200, "width": 40, "height": 20}])
    clicked = []
    monkeypatch.setattr(desktop_control.pyautogui, "click", lambda x, y: clicked.append((x, y)))
    tts = FakeTts()
    result = desktop_control.handle_screen_click("save", Registry(), tts, log, _enabled_config())

    final = result.resume("no")

    assert final == HandlerResult()
    assert clicked == []
    assert tts.said[-1] == "Never mind."


def test_click_matches_within_a_multi_word_line(monkeypatch):
    # WRatio can prefer a strong single-word match ("Button") over the
    # full reconstructed line ("OK Button") when the extra word dilutes
    # the score -- still lands within the same on-screen label either
    # way, so this asserts on the candidate set being reachable, not on
    # which specific one wins.
    _mock_ocr(monkeypatch, [
        {"text": "OK", "left": 100, "top": 200, "width": 20, "height": 20, "line_num": 0},
        {"text": "Button", "left": 125, "top": 200, "width": 40, "height": 20, "line_num": 0},
    ])
    tts = FakeTts()

    result = desktop_control.handle_screen_click("ok button", Registry(), tts, log, _enabled_config())

    assert result.question in ("Click 'OK Button'?", "Click 'Button'?")


def test_click_low_confidence_word_is_ignored(monkeypatch):
    _mock_ocr(monkeypatch, [{"text": "Save", "left": 100, "top": 200, "width": 40, "height": 20, "conf": 5}])
    tts = FakeTts()

    result = desktop_control.handle_screen_click("save", Registry(), tts, log, _enabled_config())

    assert "couldn't find" in tts.said[-1]


def test_click_tesseract_not_installed_gives_helpful_message(monkeypatch):
    def boom(label):
        raise desktop_control.pytesseract.TesseractNotFoundError()
    monkeypatch.setattr(desktop_control, "_find_label", boom)
    tts = FakeTts()

    desktop_control.handle_screen_click("save", Registry(), tts, log, _enabled_config())

    assert "Tesseract" in tts.said[-1]


def test_click_sets_requires_voice_match_from_config(monkeypatch):
    _mock_ocr(monkeypatch, [{"text": "Save", "left": 100, "top": 200, "width": 40, "height": 20}])

    result = desktop_control.handle_screen_click(
        "save", Registry(), FakeTts(), log, _enabled_config(voice_gate_enabled=True))

    assert result.requires_voice_match is True


def test_click_requires_voice_match_false_by_default(monkeypatch):
    _mock_ocr(monkeypatch, [{"text": "Save", "left": 100, "top": 200, "width": 40, "height": 20}])

    result = desktop_control.handle_screen_click("save", Registry(), FakeTts(), log, _enabled_config())

    assert result.requires_voice_match is False


# --- type ---

def test_type_empty_target_asks_what():
    tts = FakeTts()

    result = desktop_control.handle_screen_type("", Registry(), tts, log, _enabled_config())

    assert result == HandlerResult()
    assert tts.said == ["Type what?"]


def test_type_confirms_then_writes(monkeypatch):
    written = []
    monkeypatch.setattr(desktop_control.pyautogui, "write", lambda text: written.append(text))
    tts = FakeTts()

    result = desktop_control.handle_screen_type("hello world", Registry(), tts, log, _enabled_config())

    assert result.question == "Type 'hello world'?"
    assert written == []

    final = result.resume("yes")

    assert final == HandlerResult()
    assert written == ["hello world"]
    assert tts.said[-1] == "Done."


def test_type_declined_never_writes(monkeypatch):
    written = []
    monkeypatch.setattr(desktop_control.pyautogui, "write", lambda text: written.append(text))
    tts = FakeTts()
    result = desktop_control.handle_screen_type("hello", Registry(), tts, log, _enabled_config())

    final = result.resume("nope")

    assert final == HandlerResult()
    assert written == []


# --- _find_label / _candidates directly ---

def test_find_label_returns_none_when_no_words(monkeypatch):
    _mock_ocr(monkeypatch, [])

    assert desktop_control._find_label("save") is None


def test_find_label_fuzzy_matches_close_phrasing(monkeypatch):
    _mock_ocr(monkeypatch, [{"text": "Submit", "left": 10, "top": 10, "width": 60, "height": 20}])

    found = desktop_control._find_label("submit button")

    assert found is not None
    assert found[2] == "Submit"
