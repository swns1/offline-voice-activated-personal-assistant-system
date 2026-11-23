import logging

from ash.actions.results import HandlerResult
from ash.actions.stop import handle_stop
from ash.config import Config
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []
        self.stop_speaking_calls = 0

    def say(self, text):
        self.said.append(text)

    def stop_speaking(self):
        self.stop_speaking_calls += 1


def test_stop_interrupts_and_acknowledges():
    tts = FakeTts()

    result = handle_stop("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.stop_speaking_calls == 1
    assert tts.said == ["OK."]
