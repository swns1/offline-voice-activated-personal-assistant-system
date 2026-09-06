from ash.utils.paths import MODELS_DIR, resolve_wake_word_keyword


def test_bundled_name_passes_through_unchanged():
    assert resolve_wake_word_keyword("hey_jarvis") == "hey_jarvis"


def test_relative_onnx_path_resolves_against_models_dir():
    resolved = resolve_wake_word_keyword("hey_ash.onnx")
    assert resolved == str(MODELS_DIR / "hey_ash.onnx")


def test_absolute_onnx_path_is_left_alone():
    absolute = str(MODELS_DIR / "hey_ash.onnx")
    assert resolve_wake_word_keyword(absolute) == absolute


def test_non_onnx_name_never_treated_as_a_path():
    # "timer" is a real bundled openWakeWord model name -- must not be
    # resolved against MODELS_DIR just because it doesn't end in .onnx.
    assert resolve_wake_word_keyword("timer") == "timer"
