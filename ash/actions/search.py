import logging
from urllib.parse import quote_plus

from ash.audio.tts import TtsWorker
from ash.launchers.browser_launcher import BrowserLauncher
from ash.registry.schema import Registry

_browser_launcher = BrowserLauncher()


def handle_search(query: str, registry: Registry, tts: TtsWorker, log: logging.Logger) -> None:
    search_config = registry.intents.get("search")
    if search_config is None:
        log.warning("No 'search' intent configured in registry")
        tts.say("Search isn't configured yet.")
        return

    url = search_config.launch["engine_url"].format(query=quote_plus(query))
    launch = {
        "type": "browser_open",
        "url": url,
        "browser": search_config.launch.get("browser", "default"),
        "profile_directory": search_config.launch.get("profile_directory"),
    }
    _browser_launcher.launch(launch)
    log.info("Searched: %r", query)
    tts.say(f"Searching for {query}.")
