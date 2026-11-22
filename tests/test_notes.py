"""Notes and lists (ash/actions/notes.py): encrypted on this PC, and part
of the data inventory."""
import logging

import pytest

from ash.actions import notes, privacy_rights
from ash.actions.dispatcher import dispatch
from ash.config import Config
from ash.nlu.grammar import parse
from ash.privacy import secure_store
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


@pytest.fixture(autouse=True)
def notes_file(monkeypatch, tmp_path):
    monkeypatch.setattr(notes, "NOTES_PATH", tmp_path / "notes.json")


def _say(text: str, answer: str | None = None) -> str:
    tts = FakeTts()
    result = dispatch(text, Registry(), tts, log, Config())
    if not result.done:
        tts.said.append(result.question)
        if answer is not None:
            result.resume(answer)
    return tts.said[-1]


# --- notes ------------------------------------------------------------------------

def test_take_and_read_notes_newest_first():
    assert _say("Take a note: buy flowers for mom.") == "Noted: buy flowers for mom."
    assert _say("Note that the wifi password is on the fridge.") == "Noted: the wifi password is on the fridge."

    assert _say("Read my notes.") == (
        "You have 2 notes. The wifi password is on the fridge. Buy flowers for mom.")


def test_reading_many_notes_reads_the_latest_five():
    for i in range(7):
        _say(f"take a note number {i}")
    reply = _say("read my notes")
    assert reply.startswith("You have 7 notes. Here are the latest 5.")
    assert "Number 6." in reply and "Number 1." not in reply


def test_no_notes():
    assert _say("read my notes") == "You don't have any notes."


def test_delete_notes_asks_first():
    _say("take a note one")
    _say("take a note two")
    assert _say("delete my notes") == "This permanently deletes all 2 of your notes. Are you sure?"
    assert _say("delete my notes", "no") == "Okay, I'll keep them."
    assert _say("delete my notes", "Yes.") == "Your notes are deleted."
    assert _say("read my notes") == "You don't have any notes."


# --- lists --------------------------------------------------------------------------

def test_lists_end_to_end():
    assert _say("Add milk and eggs to my shopping list.") == "Added milk and eggs to a new shopping list."
    assert _say("Add bread, butter and milk to my shopping list.") == "Added bread and butter to your shopping list."
    assert _say("What's on my shopping list?") == "Your shopping list has 4 items: milk, eggs, bread, and butter."
    assert _say("Cross milk off my shopping list.") == "Removed milk from your shopping list."
    assert _say("Remove cheese from my shopping list.") == "Cheese isn't on it."
    assert _say("Add milk to my shopping list") == "Added milk to your shopping list."


def test_already_on_the_list():
    _say("add milk to my shopping list")
    assert _say("add milk to my shopping list") == "Milk is already on your shopping list."


def test_list_names_are_matched_loosely():
    _say("add call the plumber to my to-do list")
    assert _say("what's on my to do list") == "Your to-do list has 1 item: call the plumber."
    assert _say("what lists do i have") == "You have 1 list: to-do."


def test_removing_with_a_slightly_different_wording():
    _say("add tomatoes to my shopping list")
    assert _say("remove tomato from my shopping list") == "Removed tomatoes from your shopping list."


def test_clear_a_list_asks_first():
    _say("add milk, eggs and bread to my shopping list")
    assert _say("clear my shopping list") == "This deletes your shopping list and the 3 items on it. Are you sure?"
    assert _say("clear my shopping list", "yes") == "Your shopping list is deleted."
    assert _say("what's on my shopping list") == "You don't have a shopping list yet."


@pytest.mark.parametrize("said, reply", [
    ("what's on my grocery list", "You don't have a grocery list yet."),
    ("remove milk from my grocery list", "You don't have a grocery list."),
    ("add milk", "Which list? Try 'add milk to my shopping list'."),
    ("add 5 and 3", "5 plus 3 is 8."),
    ("what lists do i have", "You don't have any lists yet. Try 'add milk to my shopping list'."),
])
def test_unknown_lists_and_odd_requests(said, reply):
    assert _say(said) == reply


def test_whats_on_my_calendar_tomorrow_goes_to_the_calendar(monkeypatch):
    from ash.actions import calendar
    calls = []
    monkeypatch.setattr(calendar, "handle_calendar_list", lambda *a: calls.append(a[0]))
    dispatch("what's on my calendar tomorrow", Registry(), FakeTts(), log, Config())
    assert calls == ["calendar tomorrow"]


@pytest.mark.parametrize("said, intent", [
    ("take a note buy milk", "note_add"),
    ("delete my notes", "note_clear"),
    ("delete my shopping list", "list_clear"),
    ("delete all my data", "privacy_delete_all"),
    ("add to my calendar lunch at noon", "calendar_add"),
    ("what's on my calendar", "calendar_list"),
    ("take me to youtube", "open"),   # not a list command
])
def test_routing(said, intent):
    assert parse(said).intent == intent


# --- privacy ---------------------------------------------------------------------------

def test_notes_and_lists_are_encrypted():
    _say("take a note my locker code is 1234")
    _say("add birthday present to my secret list")
    raw = notes.NOTES_PATH.read_bytes()
    assert secure_store.is_encrypted(notes.NOTES_PATH)
    assert b"1234" not in raw and b"birthday" not in raw


def test_notes_and_lists_appear_in_what_data_do_you_have(monkeypatch, tmp_path):
    _say("take a note one")
    _say("add milk to my shopping list")
    tts = FakeTts()
    privacy_rights.handle_data_inventory("", Registry(), tts, log, Config())
    assert "1 note and 1 list" in tts.said[-1]
