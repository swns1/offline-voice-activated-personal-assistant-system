"""Weather (ash/actions/weather.py) via Open-Meteo -- faked here."""
import logging
from datetime import date

import pytest
import requests

from ash.actions import weather
from ash.actions.dispatcher import dispatch
from ash.config import Config
from ash.privacy import consent, network_log, secure_store
from ash.privacy.permission import startup_questions
from ash.registry.schema import Registry
from ash.utils import preferences

log = logging.getLogger("test")
TODAY = date(2026, 11, 23)  # a Monday


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


PLACES = {
    "manila": [{"name": "Manila", "country": "Philippines", "latitude": 14.6, "longitude": 120.98}],
    "cebu": [{"name": "Cebu City", "country": "Philippines", "latitude": 10.32, "longitude": 123.89}],
    "san jose": [
        {"name": "San Jose", "country": "United States", "latitude": 37.34, "longitude": -121.89},
        {"name": "San José", "country": "Costa Rica", "latitude": 9.93, "longitude": -84.08},
    ],
}
FORECAST = {
    "current": {"temperature_2m": 30.6, "weather_code": 2},
    "daily": {
        "weather_code": [2, 61, 3, 0, 0, 95, 1],
        "temperature_2m_max": [33.1, 31.4, 32.0, 33.0, 33.0, 30.0, 32.0],
        "temperature_2m_min": [26.2, 25.0, 25.5, 26.0, 26.0, 24.0, 25.0],
        "precipitation_probability_max": [40, 80, 10, 0, 5, 90, 25],
    },
}


@pytest.fixture
def open_meteo(monkeypatch):
    """Answers like Open-Meteo, and records every request."""
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, dict(params or {})))
        if "geocoding" in url:
            return FakeResponse({"results": PLACES.get(params["name"].lower(), [])})
        return FakeResponse(FORECAST)

    monkeypatch.setattr(requests, "get", fake_get)
    return calls


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return TODAY
    monkeypatch.setattr(weather, "date", FixedDate)


def _say(text: str, answer: str | None = None) -> str:
    tts = FakeTts()
    result = dispatch(text, Registry(), tts, log, Config())
    if not result.done:
        if answer is None:
            return result.question
        result.resume(answer)
    return tts.said[-1]


def _set_city(name="manila"):
    preferences.set("city", weather.geocode(name))


# --- understanding the request ------------------------------------------------------

@pytest.mark.parametrize("target, day, city", [
    ("", TODAY, None),
    ("tomorrow", date(2026, 11, 24), None),
    ("like tomorrow", date(2026, 11, 24), None),
    ("in cebu", TODAY, "cebu"),
    ("in cebu tomorrow", date(2026, 11, 24), "cebu"),
    ("for friday", date(2026, 11, 27), None),
    ("on friday in san jose, costa rica", date(2026, 11, 27), "san jose, costa rica"),
    ("tomorrow in cebu", date(2026, 11, 24), "cebu"),
    ("tonight", TODAY, None),
])
def test_parse_request(target, day, city):
    assert weather.parse_request(target, TODAY) == (day, city)


# --- your city ----------------------------------------------------------------------------

def test_no_city_yet(open_meteo):
    assert "I don't know your city yet" in _say("what's the weather")
    assert open_meteo == []  # nothing sent


def test_set_city_is_stored_encrypted_with_its_coordinates(open_meteo):
    assert _say("my city is Manila") == "Got it: Manila, Philippines. I'll only use it for the weather."

    assert preferences.get("city") == PLACES["manila"][0]
    assert secure_store.is_encrypted(preferences.PREFERENCES_PATH)
    assert b"Manila" not in preferences.PREFERENCES_PATH.read_bytes()
    assert _say("what's my city") == "Your city is Manila, Philippines."


def test_a_country_picks_the_right_place(open_meteo):
    _say("my city is san jose, costa rica")
    assert preferences.get("city")["country"] == "Costa Rica"


def test_unknown_city(open_meteo):
    assert _say("my city is atlantis") == "I couldn't find a place called atlantis."
    assert preferences.get("city") is None


def test_forget_city(open_meteo):
    _set_city()
    assert _say("forget my city") == "Okay, I've forgotten your city."
    assert preferences.get("city") is None
    assert _say("forget my city") == "You hadn't told me your city."


# --- weather ---------------------------------------------------------------------------------

def test_todays_weather_sends_only_coordinates(open_meteo):
    _set_city()
    open_meteo.clear()

    reply = _say("What's the weather?")

    assert reply == ("Right now in Manila: 31 degrees and partly cloudy. "
                     "Today: a high of 33 and a low of 26, with a 40% chance of rain.")
    [(url, params)] = open_meteo  # one request: the forecast -- no name lookup
    assert "api.open-meteo.com" in url
    assert (params["latitude"], params["longitude"]) == (14.6, 120.98)
    assert "Manila" not in str(params)


@pytest.mark.parametrize("said, reply", [
    ("what's the weather tomorrow", "Tomorrow in Manila: light rain, a high of 31 and a low of 25, with a 80% chance of rain."),
    ("weather on friday", "On Friday in Manila: clear skies, a high of 33 and a low of 26, with a 5% chance of rain."),
    ("what's the weather on saturday", "On Saturday in Manila: thunderstorms, a high of 30 and a low of 24, with a 90% chance of rain."),
    ("what's the weather like on thursday", "On Thursday in Manila: clear skies, a high of 33 and a low of 26."),
])
def test_other_days(open_meteo, said, reply):
    _set_city()
    assert _say(said) == reply


def test_weather_somewhere_else(open_meteo):
    _set_city()
    assert _say("what's the weather in Cebu").startswith("Right now in Cebu City: 31 degrees")
    assert ("https://geocoding-api.open-meteo.com/v1/search", ) == open_meteo[-2][:1]


def test_too_far_ahead(open_meteo):
    _set_city()
    assert _say("weather on december 25") == "I can only see the weather for the next 7 days."


@pytest.mark.parametrize("said, reply", [
    ("will it rain tomorrow", "Yes, probably: there's a 80% chance of rain tomorrow in Manila."),
    ("will it rain", "Maybe: there's a 40% chance of rain today in Manila."),
    ("do i need an umbrella on wednesday", "Probably not: just a 10% chance of rain on Wednesday in Manila."),
])
def test_rain(open_meteo, said, reply):
    _set_city()
    assert _say(said) == reply


def test_fahrenheit(open_meteo, monkeypatch):
    _set_city()
    config = Config()
    config.weather.units = "fahrenheit"
    weather.handle_weather("", Registry(), FakeTts(), log, config)
    assert open_meteo[-1][1]["temperature_unit"] == "fahrenheit"


def test_network_trouble_is_spoken(open_meteo, monkeypatch):
    _set_city()

    def down(*a, **k):
        raise requests.exceptions.ConnectionError()
    monkeypatch.setattr(requests, "get", down)
    assert _say("what's the weather") == "I couldn't get the weather right now."


# --- privacy -----------------------------------------------------------------------------------

def test_offline_mode_blocks_weather(open_meteo):
    _set_city()
    open_meteo.clear()
    consent.set_offline_mode(True)
    assert "offline mode" in _say("what's the weather")
    assert open_meteo == []


def test_asks_permission_before_the_first_lookup(open_meteo):
    consent.PRIVACY_STATE_PATH.unlink()  # nothing allowed yet
    question = _say("my city is Manila")
    assert "Open-Meteo" in question and "never your exact location" in question
    assert open_meteo == []
    assert _say("my city is Manila", "Yes.").startswith("Got it: Manila")


def test_requests_are_logged(open_meteo):
    _set_city()
    _say("what's the weather")
    domains = {e["domain"] for e in network_log.entries() if e["feature"] == "weather"}
    assert domains == {"geocoding-api.open-meteo.com", "api.open-meteo.com"}


def test_startup_asks_about_weather_only_once_a_city_is_set(open_meteo):
    consent.PRIVACY_STATE_PATH.unlink()
    consent.grant("web_search")
    assert startup_questions(Config(), FakeTts(), log).done is True  # no city: nothing to ask

    preferences.set("city", PLACES["manila"][0])
    result = startup_questions(Config(), FakeTts(), log)
    assert "Open-Meteo" in result.question
