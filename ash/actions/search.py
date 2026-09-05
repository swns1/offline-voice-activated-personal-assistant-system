import logging
from urllib.parse import quote_plus

from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.launchers.browser_launcher import BrowserLauncher
from ash.launchers.browser_profiles import resolve_profile
from ash.registry.schema import Registry

_browser_launcher = BrowserLauncher()


def handle_search(query: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> None:
    search_config = registry.intents.get("search")
    if search_config is None:
        log.warning("No 'search' intent configured in registry")
        tts.say("Search isn't configured yet.")
        return

    url = search_config.launch["engine_url"].format(query=quote_plus(query))

    browser = search_config.launch.get("browser", "default")
    if browser == "default":
        browser = config.browser.default

    spoken_profile = search_config.launch.get("profile_directory") or config.browser.profile_directory
    resolved_profile = None
    if spoken_profile:
        resolved_profile = resolve_profile(browser, spoken_profile)
        if resolved_profile is None:
            log.warning("Could not resolve browser profile %r for %s", spoken_profile, browser)

    launch = {
        "type": "browser_open",
        "url": url,
        "browser": browser,
        "profile_directory": resolved_profile,
    }
    _browser_launcher.launch(launch)
    log.info("Searched: %r", query)
    tts.say(f"Searching for {query}.")
