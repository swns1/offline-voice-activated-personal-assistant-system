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


def test_custom_onnx_path_passes_when_file_exists(tmp_path):
    model_file = tmp_path / "hey_ash.onnx"
    model_file.write_bytes(b"")

    check_wake_word_models(str(model_file))  # absolute .onnx path, no model_paths needed


def test_custom_onnx_path_exits_when_file_missing(tmp_path):
    with pytest.raises(SystemExit):
        check_wake_word_models(str(tmp_path / "does_not_exist.onnx"))


def test_custom_onnx_path_never_falls_back_to_bundled_lookup(tmp_path, monkeypatch):
    # A missing custom model must not be silently satisfied by an
    # unrelated bundled model that happens to be present.
    calls = []
    monkeypatch.setattr(
        "ash.utils.bootstrap.get_pretrained_model_paths",
        lambda inference_framework: calls.append(1) or ["some/bundled/path.onnx"],
    )
    with pytest.raises(SystemExit):
        check_wake_word_models(str(tmp_path / "hey_ash.onnx"))
    assert calls == []  # bundled lookup never even attempted
