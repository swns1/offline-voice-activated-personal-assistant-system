"""Weather, from Open-Meteo (open-meteo.com: free, no account, no key).

Privacy: Ash never works out where you are (no IP or GPS location). You
tell it your city once ("my city is Manila"); it looks the name up
once, then keeps the city's map coordinates (encrypted, in
ash/utils/preferences.py) and sends only those for forecasts. Asking
about another city ("weather in Cebu") sends that city's name. Weather
is an online feature (ash/privacy/egress.py): asked about once, logged,
and blocked in offline mode.

- "what's the weather" / "what's the weather tomorrow" / "weather in Cebu"
- "will it rain tomorrow" / "do I need an umbrella"
- "my city is Manila" / "what's my city" / "forget my city"
"""
import logging
import re
from datetime import date

from ash.actions.clock import parse_day
from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.privacy import egress
from ash.privacy.permission import ask_permission_if_needed
from ash.registry.schema import Registry
from ash.utils import preferences

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT_SECONDS = 8.0
_FORECAST_DAYS = 7

# WMO weather interpretation codes, as Open-Meteo reports them.
_CONDITIONS = {
    0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
    77: "snow", 80: "light showers", 81: "showers", 82: "heavy showers", 85: "snow showers",
    86: "snow showers", 95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail",
}
_FILLER = {"like", "outside", "forecast", "the", "weather"}


class _NoCity(Exception):
    pass


class _UnknownPlace(Exception):
    pass


# --- understanding the request -------------------------------------------------------

def parse_request(target: str, today: date) -> tuple[date, str | None]:
    """"tomorrow in cebu" / "in cebu tomorrow" -> (tomorrow, "cebu");
    "" -> (today, None). Commas stay in the place name, so "San Jose,
    Costa Rica" can pick the right country."""
    words = [w for w in target.lower().split() if w.strip(",") not in _FILLER]
    words = ["today" if w.strip(",") == "tonight" else w for w in words]

    def as_day(tokens: list[str]) -> date | None:
        text = re.sub(r"^(for|on|this)\s+", "", " ".join(t.strip(",") for t in tokens))
        return parse_day(text, today) if text else None

    day = today
    for n in (3, 2, 1):  # the day at the end: "in cebu tomorrow"
        if len(words) >= n and (found := as_day(words[-n:])) is not None:
            day, words = found, words[:-n]
            break
    else:
        for n in (3, 2, 1):  # ...or at the start: "on friday in cebu"
            if len(words) > n and (found := as_day(words[:n])) is not None:
                day, words = found, words[n:]
                break
    while words and words[0].strip(",") in ("in", "for", "at", "on"):
        words = words[1:]
    return day, (" ".join(words).strip(" ,") or None)


# --- talking to Open-Meteo -----------------------------------------------------------------

def geocode(name: str) -> dict:
    """"Manila" or "San Jose, Costa Rica" -> {"name", "country", "latitude", "longitude"}."""
    city, _, country = (part.strip() for part in name.partition(","))
    response = egress.get(
        _GEOCODE_URL, feature=egress.WEATHER.key, timeout=_TIMEOUT_SECONDS,
        params={"name": city, "count": 10, "language": "en", "format": "json"},
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    if country:
        results = [r for r in results if country.lower() in (r.get("country") or "").lower()] or results
    if not results:
        raise _UnknownPlace(name)
    best = results[0]  # Open-Meteo orders matches by relevance/population
    return {"name": best["name"], "country": best.get("country", ""),
            "latitude": best["latitude"], "longitude": best["longitude"]}


def _forecast(place: dict, config: Config) -> dict:
    response = egress.get(
        _FORECAST_URL, feature=egress.WEATHER.key, timeout=_TIMEOUT_SECONDS,
        params={
            "latitude": place["latitude"], "longitude": place["longitude"],
            "current": "temperature_2m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto", "forecast_days": _FORECAST_DAYS,
            "temperature_unit": config.weather.units,
        },
    )
    response.raise_for_status()
    return response.json()


def _place_for(city: str | None) -> dict:
    if city:
        return geocode(city)
    saved = preferences.get("city")
    if not saved:
        raise _NoCity
    return saved


# --- spoken answers -------------------------------------------------------------------------

def _degrees(value) -> str:
    return f"{round(value)} degrees"


def _when(day: date, today: date) -> str:
    """"today", "tomorrow", "on Friday"."""
    delta = (day - today).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    return f"on {day:%A}"


def _with_place(handler_name: str, target: str, tts: TtsWorker, log: logging.Logger, config: Config, retry):
    """Shared steps: permission, which day and place, and the forecast.
    Returns (day, today, place, forecast, day index), or a HandlerResult
    to return as-is (a question, or something already said)."""
    blocked = ask_permission_if_needed(egress.WEATHER.key, retry, tts=tts, log=log)
    if blocked is not None:
        return blocked
    today = date.today()
    day, city = parse_request(target, today)
    index = (day - today).days
    if not 0 <= index < _FORECAST_DAYS:
        tts.say(f"I can only see the weather for the next {_FORECAST_DAYS} days.")
        return HandlerResult()
    try:
        place = _place_for(city)
        forecast = _forecast(place, config)
    except _NoCity:
        tts.say("I don't know your city yet. Say 'my city is', then its name, or ask for the weather "
                "in a city. I only use it for the weather.")
        return HandlerResult()
    except _UnknownPlace:
        tts.say(f"I couldn't find a place called {city}.")
        return HandlerResult()
    except Exception:  # incl. egress.NetworkBlocked if offline mode came on meanwhile
        log.exception("Weather lookup failed (%s)", handler_name)
        tts.say("I couldn't get the weather right now.")
        return HandlerResult()
    return day, today, place, forecast, index


def handle_weather(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    got = _with_place("weather", target, tts, log, config,
                      retry=lambda: handle_weather(target, registry, tts, log, config))
    if isinstance(got, HandlerResult):
        return got
    day, today, place, forecast, index = got
    daily = forecast["daily"]
    condition = _CONDITIONS.get(daily["weather_code"][index], "mixed weather")
    high, low = daily["temperature_2m_max"][index], daily["temperature_2m_min"][index]
    rain = daily["precipitation_probability_max"][index]
    rain_text = f", with a {rain}% chance of rain" if rain else ""

    if index == 0:
        current = forecast["current"]
        now = _CONDITIONS.get(current["weather_code"], condition)
        tts.say(f"Right now in {place['name']}: {_degrees(current['temperature_2m'])} and {now}. "
                f"Today: a high of {round(high)} and a low of {round(low)}{rain_text}.")
    else:
        when = _when(day, today)
        tts.say(f"{when[0].upper()}{when[1:]} in {place['name']}: {condition}, a high of {round(high)} "
                f"and a low of {round(low)}{rain_text}.")
    return HandlerResult()


def handle_rain(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    got = _with_place("rain", target, tts, log, config,
                      retry=lambda: handle_rain(target, registry, tts, log, config))
    if isinstance(got, HandlerResult):
        return got
    day, today, place, forecast, index = got
    chance = forecast["daily"]["precipitation_probability_max"][index] or 0
    when = _when(day, today)
    if chance >= 50:
        answer = f"Yes, probably: there's a {chance}% chance of rain {when} in {place['name']}."
    elif chance >= 20:
        answer = f"Maybe: there's a {chance}% chance of rain {when} in {place['name']}."
    else:
        answer = f"Probably not: just a {chance}% chance of rain {when} in {place['name']}."
    tts.say(answer)
    return HandlerResult()


# --- your city --------------------------------------------------------------------------------

def handle_set_city(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    name = target.strip()
    if not name:
        tts.say("Which city?")
        return HandlerResult()
    blocked = ask_permission_if_needed(
        egress.WEATHER.key, lambda: handle_set_city(target, registry, tts, log, config), tts=tts, log=log,
    )
    if blocked is not None:
        return blocked
    try:
        place = geocode(name)
    except _UnknownPlace:
        tts.say(f"I couldn't find a place called {name}.")
        return HandlerResult()
    except Exception:
        log.exception("City lookup failed")
        tts.say("I couldn't look that city up right now.")
        return HandlerResult()
    preferences.set("city", place)
    log.info("Saved your city")
    where = f"{place['name']}, {place['country']}" if place["country"] else place["name"]
    tts.say(f"Got it: {where}. I'll only use it for the weather.")
    return HandlerResult()


def handle_whats_my_city(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    place = preferences.get("city")
    if not place:
        tts.say("You haven't told me your city. Say 'my city is', then its name.")
    else:
        where = f"{place['name']}, {place['country']}" if place.get("country") else place["name"]
        tts.say(f"Your city is {where}.")
    return HandlerResult()


def handle_forget_city(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    if preferences.delete("city"):
        log.info("Forgot your city")
        tts.say("Okay, I've forgotten your city.")
    else:
        tts.say("You hadn't told me your city.")
    return HandlerResult()
