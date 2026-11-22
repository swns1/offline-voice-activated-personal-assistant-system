"""Play/pause/skip/"what's playing" for any app (ash/actions/media.py),
through Windows' media session API -- faked here."""
import logging

import pytest

from ash.actions import media
from ash.config import Config
from ash.privacy import network_log
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


class FakeProperties:
    def __init__(self, title, artist):
        self.title, self.artist = title, artist


class FakeSession:
    def __init__(self, app="Spotify.exe", title="Bohemian Rhapsody", artist="Queen", accepts=True):
        self.source_app_user_model_id = app
        self._properties = FakeProperties(title, artist)
        self._accepts = accepts
        self.calls = []

    def _action(name):
        async def run(self):
            self.calls.append(name)
            return self._accepts
        return run

    try_pause_async = _action("pause")
    try_play_async = _action("play")
    try_skip_next_async = _action("next")
    try_skip_previous_async = _action("previous")

    async def try_get_media_properties_async(self):
        return self._properties


def _use_session(monkeypatch, session):
    class Manager:
        def get_current_session(self):
            return session

    class FakeSessionManager:
        @staticmethod
        async def request_async():
            return Manager()

    monkeypatch.setattr(media, "_SessionManager", FakeSessionManager)


def _run(handler) -> str:
    tts = FakeTts()
    handler("", Registry(), tts, log, Config())
    return tts.said[-1]


@pytest.mark.parametrize("handler, call, reply", [
    (media.handle_media_pause, "pause", "Paused."),
    (media.handle_media_resume, "play", "Resuming."),
    (media.handle_media_next, "next", "Skipping."),
    (media.handle_media_previous, "previous", "Going back."),
])
def test_controls_the_current_player(monkeypatch, handler, call, reply):
    session = FakeSession()
    _use_session(monkeypatch, session)

    assert _run(handler) == reply
    assert session.calls == [call]


def test_nothing_playing(monkeypatch):
    _use_session(monkeypatch, None)
    assert _run(media.handle_media_pause) == "Nothing is playing."
    assert _run(media.handle_media_resume) == "There's nothing to resume."
    assert _run(media.handle_media_now_playing) == "Nothing is playing."


def test_player_refuses(monkeypatch):
    _use_session(monkeypatch, FakeSession(accepts=False))
    assert _run(media.handle_media_next) == "The player didn't accept that."


@pytest.mark.parametrize("app, expected", [
    ("Spotify.exe", "Bohemian Rhapsody by Queen, in Spotify."),
    ("MSEdge", "Bohemian Rhapsody by Queen, in Edge."),
    ("Chrome", "Bohemian Rhapsody by Queen, in Chrome."),
    ("SomeUnknownApp", "Bohemian Rhapsody by Queen."),
])
def test_whats_playing_in_any_app(monkeypatch, app, expected):
    _use_session(monkeypatch, FakeSession(app=app))
    assert _run(media.handle_media_now_playing) == expected


def test_whats_playing_without_an_artist(monkeypatch):
    _use_session(monkeypatch, FakeSession(app="vlc.exe", title="Holiday video", artist=""))
    assert _run(media.handle_media_now_playing) == "Holiday video, in VLC."


def test_api_errors_are_spoken_not_raised(monkeypatch):
    class Broken:
        @staticmethod
        async def request_async():
            raise OSError("media service unavailable")

    monkeypatch.setattr(media, "_SessionManager", Broken)
    assert _run(media.handle_media_pause) == "Something went wrong controlling the media player."


def test_falls_back_to_media_keys_without_the_api(monkeypatch):
    monkeypatch.setattr(media, "_SessionManager", None)
    pressed = []
    monkeypatch.setattr(media, "_press", pressed.append)

    assert _run(media.handle_media_pause) == "Paused."
    assert _run(media.handle_media_next) == "Skipping."
    assert pressed == [media._VK_MEDIA_PLAY_PAUSE, media._VK_MEDIA_NEXT_TRACK]
    assert _run(media.handle_media_now_playing) == "I can't see what's playing on this PC."


def test_nothing_goes_online(monkeypatch):
    _use_session(monkeypatch, FakeSession())
    for handler in (media.handle_media_pause, media.handle_media_now_playing):
        _run(handler)
    assert network_log.entries() == []
