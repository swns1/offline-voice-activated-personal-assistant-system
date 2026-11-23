"""Translation, by the local AI (Ollama on this PC), so what you
translate never leaves the PC. Only works while the local AI is on
(ash.utils.ollama.ai_enabled); otherwise Ash says what it needs.

"translate good morning to Japanese", "how do you say thank you in
Spanish". For languages not written in the Latin alphabet, the reply
includes how to pronounce it, since the Windows voice can't read, say,
Japanese script aloud (the window shows the script itself).
"""
import json
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
    "You are a translator. Translate the user's text into the requested language. Reply with JSON only: "
    '{"translation": "<the translation, in that language\'s own script>", '
    '"pronunciation": "<how to pronounce it, in the Latin alphabet, only if the language is not written '
    'in the Latin alphabet; otherwise an empty string>"}. '
    "Translate naturally, as a native speaker would say it. Never explain or add anything else."
)

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


def translate(text: str, language: str, config: Config) -> tuple[str, str]:
    message = chat(config, [{"role": "user", "content": f"Language: {language}\nText: {text}"}],
                   system=_SYSTEM, format="json")
    data = json.loads(message.get("content") or "{}")
    return str(data.get("translation", "")).strip(), str(data.get("pronunciation", "")).strip()


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
    except Exception:
        log.warning("Translation failed", exc_info=True)
        tts.say("Something went wrong translating that.")
        return HandlerResult()
    if not translation:
        tts.say("I couldn't translate that.")
        return HandlerResult()
    log.info("Translated %s into %s", said(text), language)
    reply = f"In {language}: {translation}"
    if pronunciation and pronunciation.lower() != translation.lower():
        reply += f". It's pronounced {pronunciation}"
    tts.say(reply + ("" if reply.endswith((".", "!", "?", "。")) else "."))
    return HandlerResult()
