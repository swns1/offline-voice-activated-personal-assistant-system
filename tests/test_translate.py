"""Translation by the local AI (ash/actions/translate.py), with Ollama faked."""
import logging

import pytest

from ash.actions import translate
from ash.actions.dispatcher import dispatch
from ash.config import Config
from ash.privacy import egress, network_log
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


@pytest.fixture
def ai(monkeypatch):
    state = {"asked": [], "reply": "おはようございます (ohayou gozaimasu)"}
    monkeypatch.setattr(translate, "ai_enabled", lambda config: True)

    def fake_chat(config, messages, **kwargs):
        state["asked"].append((messages, kwargs))
        return {"content": state["reply"]}
    monkeypatch.setattr(translate, "chat", fake_chat)
    return state


def _run(text, config=None):
    tts = FakeTts()
    return tts, dispatch(text, Registry(), tts, log, config or Config())


def test_translates_with_pronunciation_for_other_scripts(ai):
    tts, _ = _run("translate Good morning to Japanese")
    assert tts.said == ["In Japanese: おはようございます. It's pronounced ohayou gozaimasu."]
    messages, kwargs = ai["asked"][0]
    assert messages[0]["content"] == "Translate into Japanese: Good morning"  # original capitals kept
    assert kwargs["options"] == {"temperature": 0}
    assert kwargs["model"] == "gemma3:4b" and kwargs["keep_alive"] == "1m"


def test_no_pronunciation_for_latin_alphabet_languages(ai):
    ai["reply"] = "Muchas gracias"
    tts, _ = _run("how do you say thank you very much in spanish")
    assert tts.said == ["In Spanish: Muchas gracias."]


def test_pronunciation_for_any_language_unless_it_only_repeats_it(ai):
    ai["reply"] = "Muchas gracias. (moo-chas grah-see-ahs)"
    tts, _ = _run("translate thank you very much to spanish")
    assert tts.said == ["In Spanish: Muchas gracias. It's pronounced moo-chas grah-see-ahs."]
    ai["reply"] = "Ich bin zu spät. (Ich bin zu spät)"
    tts, _ = _run("translate i'm running late to german")
    assert tts.said == ["In German: Ich bin zu spät."]


def test_gemma_translates_by_default(ai):
    _run("translate hello to french")
    assert ai["asked"][0][1]["model"] == "gemma3:4b"


def test_falls_back_to_the_main_model_if_the_translation_model_isnt_downloaded(monkeypatch):
    import requests

    monkeypatch.setattr(translate, "ai_enabled", lambda config: True)
    response = requests.Response()
    response.status_code = 404
    models = []

    def chat(config, messages, **kwargs):
        models.append(kwargs["model"])
        if kwargs["model"] == "gemma3:4b":
            raise requests.HTTPError("model not found", response=response)
        return {"content": "Bonjour"}
    monkeypatch.setattr(translate, "chat", chat)
    tts, _ = _run("translate hello to french")
    assert models == ["gemma3:4b", None]
    assert tts.said == ["In French: Bonjour."]


def test_asks_which_language_when_none_was_given(ai):
    _, result = _run("translate meet me in paris")
    assert result.question == "Into which language?"
    ai["reply"] = "Retrouve-moi à Paris"
    result.resume("French.")
    assert ai["asked"][-1][0][0]["content"] == "Translate into French: meet me in paris"


def test_without_the_local_ai(monkeypatch):
    monkeypatch.setattr(translate, "ai_enabled", lambda config: False)
    tts, _ = _run("translate hello to french")
    assert tts.said == [translate.NEEDS_AI]


def test_ollama_stopped_mid_way(ai, monkeypatch):
    def unreachable(config, messages, **kwargs):
        raise egress.NetworkUnreachable("refused")
    monkeypatch.setattr(translate, "chat", unreachable)
    tts, _ = _run("translate hello to french")
    assert tts.said == ["I can't reach the local AI right now."]


def test_nothing_leaves_the_pc(ai):
    _run("translate hello to french")
    assert network_log.entries() == []


@pytest.mark.parametrize("target, expected", [
    ("good morning to japanese", ("good morning", "Japanese")),
    ("i want to go home to french", ("i want to go home", "French")),
    ("where is the bathroom in brazilian portuguese", ("where is the bathroom", "Portuguese")),
    ("meet me in paris", ("meet me in paris", None)),
    ("hello", ("hello", None)),
])
def test_parse_request(target, expected):
    assert translate.parse_request(target) == expected


def test_the_shared_chat_helper_sends_the_right_request(monkeypatch):
    from ash.utils import ollama
    sent = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "hi"}}

    def post(url, *, feature, json, timeout):
        sent.update(url=url, feature=feature, json=json)
        return Response()
    monkeypatch.setattr(ollama.egress, "post", post)

    reply = ollama.chat(Config(), [{"role": "user", "content": "x"}], system="be brief", format="json")

    assert reply == {"content": "hi"}
    assert sent["url"] == "http://localhost:11434/api/chat" and sent["feature"] == "local_ai"
    assert sent["json"]["messages"][0] == {"role": "system", "content": "be brief"}
    assert sent["json"]["format"] == "json" and "tools" not in sent["json"]
    # Every request uses the same context size, so Ollama never reloads the model between them.
    assert sent["json"]["options"] == {"num_ctx": ollama.CONTEXT_TOKENS}
