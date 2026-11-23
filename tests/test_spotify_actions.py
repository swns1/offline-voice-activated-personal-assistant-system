import logging

from ash.actions import spotify
from ash.nlu import context

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


class FakeSpotify:
    def __init__(self, devices=None, search_result=None, playback=None):
        self._devices = devices if devices is not None else [{"id": "d1"}]
        self._search_result = search_result
        self._playback = playback
        self.calls = []

    def search(self, q, type, limit):
        self.calls.append(("search", q))
        return self._search_result or {"tracks": {"items": []}}

    def devices(self):
        return {"devices": self._devices}

    def start_playback(self, uris=None):
        self.calls.append(("start_playback", uris))

    def pause_playback(self):
        self.calls.append(("pause_playback",))

    def next_track(self):
        self.calls.append(("next_track",))

    def previous_track(self):
        self.calls.append(("previous_track",))

    def current_playback(self):
        return self._playback


def _track_result(name="Bohemian Rhapsody", uri="spotify:track:123"):
    return {"tracks": {"items": [{"name": name, "uri": uri}]}}


def test_play_starts_playback_on_active_device():
    client = FakeSpotify(search_result=_track_result())
    tts = FakeTts()

    spotify._play(client, "bohemian rhapsody", tts, log)

    assert ("start_playback", ["spotify:track:123"]) in client.calls
    assert any("Bohemian Rhapsody" in msg for msg in tts.said)


def test_play_remembers_the_track():
    client = FakeSpotify(search_result=_track_result())

    spotify._play(client, "bohemian rhapsody", FakeTts(), log)

    assert context.resolve_target("spotify_play", "it") == "Bohemian Rhapsody"


def test_play_no_track_found_says_so():
    client = FakeSpotify(search_result={"tracks": {"items": []}})
    tts = FakeTts()

    spotify._play(client, "some nonexistent song", tts, log)

    assert not any(call[0] == "start_playback" for call in client.calls)
    assert any("couldn't find" in msg for msg in tts.said)


def test_play_with_no_active_device_says_so(monkeypatch):
    client = FakeSpotify(devices=[], search_result=_track_result())
    tts = FakeTts()
    monkeypatch.setattr(spotify.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(spotify._uri_launcher, "launch", lambda launch: None)

    spotify._play(client, "bohemian rhapsody", tts, log)

    assert not any(call[0] == "start_playback" for call in client.calls)
    assert any("Open Spotify" in msg for msg in tts.said)


def test_execute_pause_speaks_on_success():
    client = FakeSpotify()
    tts = FakeTts()

    spotify._execute(client, lambda c: c.pause_playback(), "Paused.", tts, log)

    assert ("pause_playback",) in client.calls
    assert tts.said == ["Paused."]


def test_execute_swallows_exceptions_and_speaks_failure():
    client = FakeSpotify()
    tts = FakeTts()

    def boom(c):
        raise RuntimeError("api down")

    spotify._execute(client, boom, "Paused.", tts, log)

    assert tts.said == ["Something went wrong with Spotify."]


def test_now_playing_speaks_track_and_artist():
    client = FakeSpotify(playback={
        "item": {"name": "Bohemian Rhapsody", "artists": [{"name": "Queen"}]}
    })
    tts = FakeTts()

    spotify._now_playing(client, tts)

    assert tts.said == ["Bohemian Rhapsody by Queen."]


def test_now_playing_nothing_playing():
    client = FakeSpotify(playback=None)
    tts = FakeTts()

    spotify._now_playing(client, tts)

    assert tts.said == ["Nothing is playing."]


def test_get_client_returns_none_when_disabled():
    from ash.config import Config

    spotify._client = None
    tts = FakeTts()
    config = Config()  # spotify.enabled defaults to False

    result = spotify._get_client(config, tts)

    assert result is None
    assert any("set up" in msg for msg in tts.said)
