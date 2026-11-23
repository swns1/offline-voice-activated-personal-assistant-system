"""Two related but distinct actions:

- handle_search ("search for X" / "what is X" / "look up X"): tries to
  answer directly via DuckDuckGo's Instant Answer API -- free, no
  account or key, but real coverage is patchy (great for named topics
  like "Eiffel Tower" or "Python programming language", nothing for
  question-style phrasing, calculations, or dictionary lookups via this
  endpoint -- confirmed directly against the live API, not assumed).
  Gated behind config.search.enabled since it's a real, if small,
  departure from fully-offline operation.

- handle_browser_search ("search in browser for X"): the original
  behavior, kept as an explicit phrasing for when you actually want to
  browse instead of hear an answer -- opens a browser tab, with browser
  profile resolution.
"""
import logging
from urllib.parse import quote_plus

from ash.actions import calculator
from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.launchers.browser_launcher import BrowserLauncher
from ash.launchers.browser_profiles import list_profiles, resolve_profile
from ash.nlu.context import remember_search
from ash.privacy import egress
from ash.privacy.permission import ask_permission_if_needed
from ash.privacy.redact import said
from ash.registry.schema import Registry

_browser_launcher = BrowserLauncher()
_DDG_TIMEOUT_SECONDS = 5.0
_ANSWER_FIELDS = ("Answer", "AbstractText", "Definition")


def handle_search(query: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    # "what's 15% of 80" / "what's 5 miles in km": worked out on this PC,
    # never sent to a search engine.
    local = calculator.answer(query)
    if local is not None:
        tts.say(local)
        return HandlerResult()

    if not config.search.enabled:
        tts.say(f"Web search is turned off. Try 'search in browser for {query}'.")
        return HandlerResult()

    blocked = ask_permission_if_needed(
        egress.WEB_SEARCH.key, lambda: handle_search(query, registry, tts, log, config), tts=tts, log=log,
    )
    if blocked is not None:
        return blocked

    answer = _query_duckduckgo(query)
    if answer is None:
        log.info("No DuckDuckGo answer for %s", said(query))
        tts.say(f"I couldn't find an answer for {query}. Try 'search in browser for {query}'.")
        return HandlerResult()

    remember_search(query)
    log.info("Answered %s via DuckDuckGo", said(query))
    tts.say(answer)
    return HandlerResult()


def _query_duckduckgo(query: str) -> str | None:
    try:
        response = egress.get(
            "https://api.duckduckgo.com/", feature=egress.WEB_SEARCH.key,
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            timeout=_DDG_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    for field in _ANSWER_FIELDS:
        value = data.get(field)
        if value:
            return value

    for item in data.get("RelatedTopics") or []:
        text = item.get("Text")
        if text:
            return text

    return None


def handle_browser_search(query: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    search_config = registry.intents.get("search")
    if search_config is None:
        log.warning("No 'search' intent configured in registry")
        tts.say("Search isn't configured yet.")
        return HandlerResult()

    url = search_config.launch["engine_url"].format(query=quote_plus(query))

    browser = search_config.launch.get("browser", "default")
    if browser == "default":
        browser = config.browser.default

    spoken_profile = search_config.launch.get("profile_directory") or config.browser.profile_directory
    if spoken_profile:
        resolved_profile = resolve_profile(browser, spoken_profile)
        if resolved_profile is None:
            log.warning("Could not resolve browser profile %r for %s", spoken_profile, browser)
        return _run_browser_search(query, url, browser, resolved_profile, tts, log)

    profiles = list_profiles(browser)
    if len(profiles) > 1:
        return _ask_which_profile(query, url, browser, profiles, tts, log)

    return _run_browser_search(query, url, browser, None, tts, log)


def _run_browser_search(query: str, url: str, browser: str, profile_directory: str | None,
                         tts: TtsWorker, log: logging.Logger) -> HandlerResult:
    launch = {
        "type": "browser_open",
        "url": url,
        "browser": browser,
        "profile_directory": profile_directory,
    }
    _browser_launcher.launch(launch)
    log.info("Searched in browser: %s", said(query))
    remember_search(query)
    tts.say(f"Searching for {query}.")
    return HandlerResult()


def _ask_which_profile(query: str, url: str, browser: str, profiles: dict[str, str],
                        tts: TtsWorker, log: logging.Logger) -> HandlerResult:
    display_names = list(profiles.keys())[:2]
    question = f"Which {browser} profile, {display_names[0]} or {display_names[1]}?"

    def resume(answer: str) -> HandlerResult:
        directory_key = profiles.get(answer.strip().lower())
        if directory_key is None:
            log.info("Follow-up %s didn't match a browser profile", said(answer))
            tts.say("Never mind.")
            return HandlerResult()
        return _run_browser_search(query, url, browser, directory_key, tts, log)

    return HandlerResult(done=False, question=question, resume=resume)
