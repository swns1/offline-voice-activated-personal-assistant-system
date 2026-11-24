"""Translation, by the local AI (Ollama on this PC), so what you
translate never leaves the PC. Only works while the local AI is on
(ash.utils.ollama.ai_enabled); otherwise Ash says what it needs.

"translate good morning to Japanese", "how do you say thank you in
Spanish". For languages not written in the Latin alphabet, the reply
includes how to pronounce it, since the Windows voice can't read, say,
Japanese script aloud (the window shows the script itself).
"""
import logging
import re

from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.nlu.context import original_case
from ash.privacy import egress
from ash.privacy.redact import said
from ash.registry.schema import Registry
from ash.utils.ollama import ai_enabled, chat

log = logging.getLogger("ash")

LANGUAGES = {
    "afrikaans", "arabic", "bengali", "bulgarian", "burmese", "cantonese", "catalan", "cebuano", "chinese",
    "croatian", "czech", "danish", "dutch", "english", "estonian", "filipino", "finnish", "french", "german",
    "greek", "gujarati", "hawaiian", "hebrew", "hindi", "hungarian", "icelandic", "ilocano", "indonesian",
    "irish", "italian", "japanese", "javanese", "kannada", "khmer", "korean", "lao", "latin", "latvian",
    "lithuanian", "malay", "malayalam", "mandarin", "marathi", "mongolian", "nepali", "norwegian", "persian",
    "polish", "portuguese", "punjabi", "romanian", "russian", "serbian", "sinhala", "slovak", "slovenian",
    "spanish", "swahili", "swedish", "tagalog", "tamil", "telugu", "thai", "turkish", "ukrainian", "urdu",
    "vietnamese", "welsh", "zulu", "bisaya", "hiligaynon", "kapampangan", "waray", "bikol",
}

_SPLIT = re.compile(r"^(?P<text>.+?)\s+(?:to|into|in)\s+(?P<language>[a-z]+(?:\s+[a-z]+)?)$")

_SYSTEM = (
    "You are a translator. Translate the user's text into the language they name, as a native speaker would "
    "say it. Reply with the translation, in that language's own writing system, then how to pronounce it, "
    "spelled for an English speaker, in parentheses. No explanations, no quotes."
)
# Plain text rather than JSON: asked for JSON, llama3.2 returned an
# empty translation for Japanese every time (measured).
_WITH_PRONUNCIATION = re.compile(r"^(?P<text>.+?)\s*[(\uff08](?P<pronunciation>[^()\uff08\uff09]+)[)\uff09]\s*$", re.DOTALL)

NEEDS_AI = ("Translation needs the local AI, which isn't running. Install Ollama and run "
            "'ollama pull llama3.2', and Ash will use it automatically.")


def parse_request(target: str) -> tuple[str, str | None]:
    """"good morning to japanese" -> ("good morning", "Japanese").
    The language is None if none was given (or it isn't one Ash knows):
    "translate meet me in paris" mustn't become a translation into
    "Paris"."""
    target = target.strip().strip("\"'")
    match = _SPLIT.match(target)
    if match is None:
        return target, None
    language = match["language"].split()[-1]  # "brazilian portuguese" -> portuguese
    if language not in LANGUAGES:
        return target, None
    return match["text"].strip().strip("\"'"), language.capitalize()


def _plain(text: str) -> str:
    return re.sub(r"[^\w]", "", text).lower()


def translate(text: str, language: str, config: Config) -> tuple[str, str]:
    """(translation, how to pronounce it -- or "" if the model gave none)."""
    message = _ask(text, language, config, config.ollama.translation_model)
    reply = (message.get("content") or "").strip().strip("\"\u201c\u201d")
    match = _WITH_PRONUNCIATION.match(reply)
    if match is None:
        return reply, ""
    translation, pronunciation = match["text"].strip(), match["pronunciation"].strip()
    if _plain(pronunciation) == _plain(translation):  # "Ich bin zu spät. (Ich bin zu spät)"
        pronunciation = ""
    return translation, pronunciation


def _ask(text: str, language: str, config: Config, model: str | None) -> dict:
    """Ask the translation model; if it isn't downloaded, the main model."""
    try:
        # A separate translation model is let go of a minute later, rather
        # than staying loaded next to the main model: two 3-4B models on
        # an 8 GB graphics card left too little room (measured: every
        # request several times slower).
        return chat(config, [{"role": "user", "content": f"Translate into {language}: {text}"}], system=_SYSTEM,
                    options={"temperature": 0}, model=model, keep_alive="1m" if model else None)
    except egress.RequestError as error:
        if model is None or getattr(error.response, "status_code", None) != 404:
            raise
        log.warning("Translation model %s isn't downloaded (ollama pull %s); using %s",
                    model, model, config.ollama.model)
        return _ask(text, language, config, None)


def handle_translate(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger,
                     config: Config) -> HandlerResult:
    if not ai_enabled(config):
        tts.say(NEEDS_AI)
        return HandlerResult()
    text, language = parse_request(target)
    if not text:
        tts.say("What should I translate? Say, for example, 'translate good morning to Japanese'.")
        return HandlerResult()
    text = original_case(text)
    if language is None:
        def resume(answer: str) -> HandlerResult:
            _, chosen = parse_request(f"x to {answer.strip().lower().rstrip('.')}")
            if chosen is None:
                tts.say("I don't know that language, sorry.")
                return HandlerResult()
            return _translate_and_say(text, chosen, tts, log, config)
        return HandlerResult(done=False, question="Into which language?", resume=resume)
    return _translate_and_say(text, language, tts, log, config)


def _translate_and_say(text: str, language: str, tts: TtsWorker, log: logging.Logger,
                       config: Config) -> HandlerResult:
    try:
        translation, pronunciation = translate(text, language, config)
    except egress.NetworkUnreachable:
        tts.say("I can't reach the local AI right now.")
        return HandlerResult()
    except egress.RequestError:
        log.warning("Translation failed", exc_info=True)
        tts.say("Something went wrong translating that.")
        return HandlerResult()
    except Exception:
        log.warning("Translation failed", exc_info=True)
        tts.say("Something went wrong translating that.")
        return HandlerResult()
    if not translation:
        tts.say("I couldn't translate that.")
        return HandlerResult()
    log.info("Translated %s into %s", said(text), language)
    reply = f"In {language}: {translation.rstrip('.')}"
    if pronunciation:
        reply += f". It's pronounced {pronunciation.rstrip('.')}"
    tts.say(reply + ("" if reply.endswith((".", "!", "?", "。")) else "."))
    return HandlerResult()
