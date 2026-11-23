import sys
import types

import numpy as np
import pytest

from ash.audio import tts as tts_module
from ash.audio.tts import TtsWorker


class FakeEngine:
    def __init__(self):
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1


def test_stop_speaking_drains_queue_and_stops_engine():
    worker = TtsWorker()
    worker.say("first")
    worker.say("second")
    fake_engine = FakeEngine()
    worker._engine = fake_engine

    worker.stop_speaking()

    assert worker._queue.empty()
    assert fake_engine.stop_calls == 1


def test_stop_speaking_before_engine_exists_is_a_noop():
    worker = TtsWorker()
    worker.say("queued")

    worker.stop_speaking()  # _engine is still None -- must not raise

    assert worker._queue.empty()


def test_stop_speaking_with_empty_queue_still_stops_engine():
    worker = TtsWorker()
    fake_engine = FakeEngine()
    worker._engine = fake_engine

    worker.stop_speaking()

    assert fake_engine.stop_calls == 1


def test_is_speaking_false_initially():
    worker = TtsWorker()
    assert worker.is_speaking() is False


def test_is_speaking_reflects_internal_event():
    worker = TtsWorker()

    worker._speaking.set()
    assert worker.is_speaking() is True

    worker._speaking.clear()
    assert worker.is_speaking() is False


# --- voice engines ---------------------------------------------------------------------





class _FakeSapi:
    name = "windows"

    def __init__(self, rate=180, voice_id=None):
        pass


def test_piper_falls_back_to_the_windows_voice_when_the_voice_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(tts_module, "SapiEngine", _FakeSapi)
    engine = tts_module.make_engine("piper", tmp_path / "missing.onnx")
    assert engine.name == "windows"


def test_the_windows_voice_by_default(monkeypatch):
    monkeypatch.setattr(tts_module, "SapiEngine", _FakeSapi)
    assert tts_module.make_engine().name == "windows"


class _FakePiperVoice:
    def __init__(self, on_chunk=None):
        self.texts = []
        self.on_chunk = on_chunk

    def synthesize(self, text):
        self.texts.append(text)
        for i, _sentence in enumerate(text.split(". ")):
            if self.on_chunk:
                self.on_chunk(i)
            yield types.SimpleNamespace(audio_int16_array=np.full(10, i, dtype=np.int16), sample_rate=22050)


@pytest.fixture
def speakers(monkeypatch):
    played = []
    fake_sd = types.SimpleNamespace(play=lambda audio, rate: played.append(int(audio[0])),
                                    wait=lambda: None, stop=lambda: played.append("stop"))
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    return played


def _piper(voice) -> tts_module.PiperEngine:
    engine = tts_module.PiperEngine.__new__(tts_module.PiperEngine)
    engine._voice = voice
    engine._stopped = tts_module.threading.Event()
    return engine


def test_piper_plays_sentence_by_sentence(speakers):
    _piper(_FakePiperVoice()).speak("One. Two. Three")
    assert speakers == [0, 1, 2]


def test_stopping_piper_skips_the_remaining_sentences(speakers):
    engine = _piper(None)
    engine._voice = _FakePiperVoice(on_chunk=lambda i: engine.stop() if i == 1 else None)
    engine.speak("One. Two. Three")
    assert speakers == [0, "stop"]


def test_piper_warms_up_when_loaded(monkeypatch, tmp_path):
    voice = _FakePiperVoice()
    monkeypatch.setitem(sys.modules, "piper",
                        types.SimpleNamespace(PiperVoice=types.SimpleNamespace(load=lambda path: voice)))
    tts_module.PiperEngine(tmp_path / "v.onnx")
    assert voice.texts == ["Ready."]
