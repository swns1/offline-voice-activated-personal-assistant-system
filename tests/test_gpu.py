"""Speech recognition on the GPU (ash/audio/gpu.py, ash/audio/stt.py),
with the GPU and Whisper faked: these behave the same on any PC."""
import os
import sys
import types

import pytest

from ash.audio import gpu, stt
from ash.privacy.egress import MODEL_DOWNLOAD, OfflineModeError


@pytest.fixture
def whisper(monkeypatch):
    loads = []

    class FakeWhisper:
        fail_on_gpu = False

        def __init__(self, size, device, compute_type, local_files_only=False):
            loads.append((device, compute_type))
            self.device = device

        def transcribe(self, audio, **kwargs):
            if self.device == "cuda" and FakeWhisper.fail_on_gpu:
                raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
            return [], None

    monkeypatch.setattr(stt, "WhisperModel", FakeWhisper)
    return FakeWhisper, loads


def test_auto_uses_the_gpu_when_it_works(monkeypatch, whisper):
    _, loads = whisper
    monkeypatch.setattr(gpu, "cuda_available", lambda: True)
    speech = stt.SpeechToText(device="auto")
    assert speech.device == "cuda" and loads == [("cuda", "int8_float16")]


def test_auto_uses_the_cpu_without_a_usable_gpu(whisper):
    _, loads = whisper
    speech = stt.SpeechToText(device="auto")  # conftest: no GPU
    assert speech.device == "cpu" and loads == [("cpu", "int8")]


def test_a_gpu_that_fails_at_the_first_transcription_falls_back_to_the_cpu(monkeypatch, whisper):
    fake, loads = whisper
    fake.fail_on_gpu = True
    monkeypatch.setattr(gpu, "cuda_available", lambda: True)
    speech = stt.SpeechToText(device="auto")
    assert speech.device == "cpu" and loads == [("cuda", "int8_float16"), ("cpu", "int8")]


def test_offline_mode_isnt_mistaken_for_a_gpu_problem(monkeypatch, whisper):
    monkeypatch.setattr(gpu, "cuda_available", lambda: True)

    def blocked(*args, **kwargs):
        raise OfflineModeError(MODEL_DOWNLOAD, "offline mode is on")
    monkeypatch.setattr(stt, "load_whisper_model", blocked)
    with pytest.raises(OfflineModeError):
        stt.SpeechToText(device="auto")


# --- finding the GPU -------------------------------------------------------------------

def _fake_ctranslate2(monkeypatch, devices):
    monkeypatch.setitem(sys.modules, "ctranslate2", types.SimpleNamespace(get_cuda_device_count=lambda: devices))


def _real_cuda_available():
    # conftest replaces gpu.cuda_available; test the real one.
    import importlib
    return importlib.reload(gpu).cuda_available


def test_no_nvidia_gpu(monkeypatch):
    check = _real_cuda_available()
    _fake_ctranslate2(monkeypatch, 0)
    assert check() is False


def test_a_gpu_without_the_library_says_how_to_add_it(monkeypatch, caplog):
    check = _real_cuda_available()
    _fake_ctranslate2(monkeypatch, 1)
    monkeypatch.setitem(sys.modules, "nvidia.cublas", None)  # not installed
    caplog.set_level("INFO")
    assert check() is False
    assert "requirements-gpu.txt" in caplog.text


def test_the_library_is_put_on_this_processs_path(monkeypatch, tmp_path):
    check = _real_cuda_available()
    _fake_ctranslate2(monkeypatch, 1)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "cublas64_12.dll").write_bytes(b"")
    cublas = types.SimpleNamespace(__path__=[str(tmp_path)])
    monkeypatch.setitem(sys.modules, "nvidia", types.SimpleNamespace(cublas=cublas))
    monkeypatch.setitem(sys.modules, "nvidia.cublas", cublas)
    monkeypatch.setenv("PATH", r"C:\Windows")
    assert check() is True
    assert os.environ["PATH"].split(os.pathsep)[0] == str(tmp_path / "bin")
