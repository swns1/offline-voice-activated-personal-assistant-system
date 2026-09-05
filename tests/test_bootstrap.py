import pytest

from ash.utils.bootstrap import check_wake_word_models


def test_passes_when_model_file_exists(tmp_path):
    model_file = tmp_path / "hey_jarvis_v0.1.onnx"
    model_file.write_bytes(b"")

    check_wake_word_models("hey_jarvis", model_paths=[str(model_file)])


def test_exits_when_model_file_missing(tmp_path):
    with pytest.raises(SystemExit):
        check_wake_word_models("hey_jarvis", model_paths=[str(tmp_path / "hey_jarvis_v0.1.onnx")])


def test_exits_when_no_paths_given():
    with pytest.raises(SystemExit):
        check_wake_word_models("hey_jarvis", model_paths=[])
