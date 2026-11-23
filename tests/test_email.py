"""Email through Outlook (ash/actions/email.py), with Outlook faked."""
import logging

import pytest

from ash.actions import email
from ash.actions.dispatcher import dispatch
from ash.actions.results import YES_NO
from ash.config import Config
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


def _config(enabled=True) -> Config:
    config = Config()
    config.email.enabled = enabled
    return config


@pytest.fixture
def outlook(monkeypatch):
    state = {"sent": [], "contacts": {"anna": email.Recipient("Anna Reyes", "anna@example.com")}}
    monkeypatch.setattr(email, "resolve", lambda name: state["contacts"].get(name.lower()))
    monkeypatch.setattr(email, "send", lambda r, subject, body: state["sent"].append((r.address, subject, body)))
    monkeypatch.setattr(email, "unread_and_latest", lambda count=3: (2, [
        email.Message("GitHub", "CI passed"), email.Message("Anna Reyes", "Lunch?")]))
    return state


def _run(text, config=None):
    tts = FakeTts()
    result = dispatch(text, Registry(), tts, log, config or _config())
    return tts, result


def test_off_unless_turned_on(outlook):
    tts, _ = _run("check my email", _config(enabled=False))
    assert "isn't set up" in tts.said[-1]
    tts, _ = _run("email anna saying hi", _config(enabled=False))
    assert "isn't set up" in tts.said[-1] and outlook["sent"] == []


def test_check_reads_senders_and_subjects_only(outlook):
    tts, _ = _run("check my email")
    assert tts.said == ["You have 2 unread emails. The latest: from GitHub: CI passed; from Anna Reyes: Lunch?."]


def test_outlook_missing(monkeypatch):
    def broken(count=3):
        raise OSError("Invalid class string")
    monkeypatch.setattr(email, "unread_and_latest", broken)
    tts, _ = _run("check my email")
    assert tts.said == [email.UNREACHABLE]


def test_sending_says_exactly_what_and_to_whom_and_waits_for_yes(outlook):
    tts, result = _run("Email Anna saying I'm running late, tell John to start without me")

    assert not result.done and result.choices == YES_NO
    assert result.question == (
        "I'll email Anna Reyes, anna@example.com, with the subject 'I'm running late, tell John to start without…', "
        "saying: 'I'm running late, tell John to start without me.' Send it?")
    assert outlook["sent"] == []

    result.resume("yes")
    assert outlook["sent"] == [("anna@example.com", "I'm running late, tell John to start without…",
                                "I'm running late, tell John to start without me.")]
    assert tts.said[-1] == "Sent to Anna Reyes."


def test_anything_but_yes_sends_nothing(outlook):
    _, result = _run("email anna saying hi")
    result.resume("no wait")
    assert outlook["sent"] == []


def test_asks_for_the_message_if_you_only_said_who(outlook):
    _, result = _run("send an email to anna")
    assert result.question == "What should the email to anna say?"
    confirm = result.resume("See you at 5")
    assert "saying: 'See you at 5.'" in confirm.question
    confirm.resume("yes")
    assert outlook["sent"][0][2] == "See you at 5."


def test_an_unknown_or_ambiguous_name_sends_nothing(outlook):
    tts, result = _run("email zed saying hi")
    assert result.done and outlook["sent"] == []
    assert "couldn't find exactly one contact called zed" in tts.said[-1]


def test_an_address_said_out_loud(outlook):
    _, result = _run("email bob at example dot com saying hello")
    assert "I'll email bob@example.com," in result.question


def test_nothing_about_the_email_reaches_the_log(outlook, caplog):
    caplog.set_level(logging.INFO)
    _, result = _run("email anna saying the secret plan")
    result.resume("yes")
    assert "secret" not in caplog.text and "anna@example.com" not in caplog.text


@pytest.mark.parametrize("target, expected", [
    ("anna saying hi there", ("anna", "hi there")),
    ("to anna that says hi", ("anna", "hi")),
    ("my boss and tell him I'm sick", ("my boss", "I'm sick")),
    ("anna", ("anna", "")),
])
def test_parse_send(target, expected):
    assert email.parse_send(target) == expected


def test_real_outlook_is_never_used_in_tests():
    with pytest.raises(RuntimeError, match="real Outlook"):
        email.unread_and_latest()
