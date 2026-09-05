import logging
from urllib.parse import quote_plus

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.launchers.browser_launcher import BrowserLauncher
from ash.launchers.browser_profiles import list_profiles, resolve_profile
from ash.registry.schema import Registry

_browser_launcher = BrowserLauncher()


def handle_search(query: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
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
        return _run_search(query, url, browser, resolved_profile, tts, log)

    profiles = list_profiles(browser)
    if len(profiles) > 1:
        return _ask_which_profile(query, url, browser, profiles, tts, log)

    return _run_search(query, url, browser, None, tts, log)


def _run_search(query: str, url: str, browser: str, profile_directory: str | None,
                 tts: TtsWorker, log: logging.Logger) -> HandlerResult:
    launch = {
        "type": "browser_open",
        "url": url,
        "browser": browser,
        "profile_directory": profile_directory,
    }
    _browser_launcher.launch(launch)
    log.info("Searched: %r", query)
    tts.say(f"Searching for {query}.")
    return HandlerResult()


def _ask_which_profile(query: str, url: str, browser: str, profiles: dict[str, str],
                        tts: TtsWorker, log: logging.Logger) -> HandlerResult:
    display_names = list(profiles.keys())[:2]
    question = f"Which {browser} profile, {display_names[0]} or {display_names[1]}?"

    def resume(answer: str) -> HandlerResult:
        directory_key = profiles.get(answer.strip().lower())
        if directory_key is None:
            log.info("Follow-up %r didn't match a browser profile", answer)
            tts.say("Never mind.")
            return HandlerResult()
        return _run_search(query, url, browser, directory_key, tts, log)

    return HandlerResult(done=False, question=question, resume=resume)
