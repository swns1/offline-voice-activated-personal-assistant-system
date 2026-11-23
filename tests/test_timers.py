import itertools
import json
import logging
import time

import pytest

from ash.actions import timers
from ash.actions.results import HandlerResult
from ash.config import Config
from ash.privacy import secure_store
from ash.registry.schema import Registry

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


class FakeTimer:
    """Stands in for threading.Timer -- captures the schedule instead of
    running a real background thread; tests fire it manually."""
    instances: list["FakeTimer"] = []

    def __init__(self, seconds, fn):
        self.seconds = seconds
        self.fn = fn
        self.daemon = False
        self.started = False
        self.cancelled = False
        FakeTimer.instances.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def trigger(self):
        self.fn()


@pytest.fixture(autouse=True)
def _reset_timers_state(monkeypatch, tmp_path):
    timers._active.clear()
    monkeypatch.setattr(timers, "_ids", itertools.count(1))
    FakeTimer.instances.clear()
    monkeypatch.setattr(timers.threading, "Timer", FakeTimer)
    monkeypatch.setattr(timers, "show_toast", lambda title, body, log=None: None)
    monkeypatch.setattr(timers, "TIMERS_STATE_PATH", tmp_path / "timers.json")
    yield


def test_timer_set_schedules_and_confirms():
    tts = FakeTts()

    result = timers.handle_timer_set("5 minutes", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.said == ["Timer set for 5 minutes."]
    assert len(FakeTimer.instances) == 1
    assert FakeTimer.instances[0].seconds == 300
    assert FakeTimer.instances[0].started is True


def test_timer_fires_and_speaks_message_then_clears():
    tts = FakeTts()
    timers.handle_timer_set("5 minutes to check the oven", Registry(), tts, log, Config())

    FakeTimer.instances[0].trigger()

    assert "check the oven" in tts.said[-1]
    assert len(timers._active) == 0


def test_timer_fires_a_toast_notification(monkeypatch):
    toasts = []
    monkeypatch.setattr(timers, "show_toast", lambda title, body, log=None: toasts.append((title, body)))
    tts = FakeTts()
    timers.handle_timer_set("5 minutes to check the oven", Registry(), tts, log, Config())

    FakeTimer.instances[0].trigger()

    assert toasts == [("Ash", "check the oven")]


def test_timer_with_no_message_says_times_up():
    tts = FakeTts()
    timers.handle_timer_set("5 minutes", Registry(), tts, log, Config())

    FakeTimer.instances[0].trigger()

    assert tts.said[-1] == "Time's up."


def test_timer_set_no_duration_asks_follow_up():
    tts = FakeTts()

    result = timers.handle_timer_set("please", Registry(), tts, log, Config())

    assert result.done is False
    assert "how long" in result.question.lower()
    assert tts.said == []


def test_timer_set_follow_up_resolves():
    tts = FakeTts()
    result = timers.handle_timer_set("please", Registry(), tts, log, Config())

    final = result.resume("10 seconds")

    assert final == HandlerResult()
    assert "10 seconds" in tts.said[-1]
    assert len(FakeTimer.instances) == 1


def test_timer_set_follow_up_unresolved_says_never_mind():
    tts = FakeTts()
    result = timers.handle_timer_set("please", Registry(), tts, log, Config())

    final = result.resume("I don't know")

    assert final == HandlerResult()
    assert tts.said == ["Never mind."]
    assert FakeTimer.instances == []


def test_timer_set_with_absolute_time():
    tts = FakeTts()

    result = timers.handle_timer_set("3pm", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert len(FakeTimer.instances) == 1
    assert FakeTimer.instances[0].seconds > 0
    assert "Timer set for" in tts.said[-1]


def test_reminder_set_with_absolute_time_and_message():
    tts = FakeTts()

    timers.handle_reminder_set("3pm to check the oven", Registry(), tts, log, Config())

    assert len(FakeTimer.instances) == 1
    assert "check the oven" in tts.said[-1]


def test_reminder_set_speaks_message_and_time():
    tts = FakeTts()

    result = timers.handle_reminder_set("5 minutes to call mom", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "call mom" in tts.said[-1]
    assert "5 minutes" in tts.said[-1]


def test_reminder_set_with_no_message():
    tts = FakeTts()

    timers.handle_reminder_set("5 minutes", Registry(), tts, log, Config())

    assert tts.said == ["I'll remind you in 5 minutes."]


def test_timer_cancel_cancels_all_active():
    tts = FakeTts()
    timers.handle_timer_set("5 minutes", Registry(), tts, log, Config())
    timers.handle_timer_set("10 minutes", Registry(), tts, log, Config())

    result = timers.handle_timer_cancel("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert all(t.cancelled for t in FakeTimer.instances)
    assert len(timers._active) == 0
    assert tts.said[-1] == "Cancelled 2 timers."


def test_timer_cancel_with_none_active():
    tts = FakeTts()

    timers.handle_timer_cancel("", Registry(), tts, log, Config())

    assert tts.said == ["You don't have any timers running."]


def test_timer_list_speaks_active_timers():
    tts = FakeTts()
    timers.handle_timer_set("5 minutes to check the oven", Registry(), tts, log, Config())

    result = timers.handle_timer_list("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "check the oven" in tts.said[-1]


def test_timer_list_with_none_active():
    tts = FakeTts()

    timers.handle_timer_list("", Registry(), tts, log, Config())

    assert tts.said == ["You don't have any timers running."]


def test_max_active_timers_enforced():
    tts = FakeTts()
    for _ in range(timers._MAX_ACTIVE_TIMERS):
        timers.handle_timer_set("1 minute", Registry(), tts, log, Config())

    result = timers.handle_timer_set("1 minute", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert tts.said[-1] == "You already have too many timers running."
    assert len(FakeTimer.instances) == timers._MAX_ACTIVE_TIMERS


def test_persist_writes_active_timers_to_disk():
    tts = FakeTts()
    timers.handle_timer_set("5 minutes to check the oven", Registry(), tts, log, Config())

    saved = secure_store.read_json(timers.TIMERS_STATE_PATH)

    assert len(saved) == 1
    assert saved[0]["label"] == "check the oven"
    assert saved[0]["fires_at_wall"] > time.time()


def test_persist_removes_entry_on_fire():
    tts = FakeTts()
    timers.handle_timer_set("5 minutes", Registry(), tts, log, Config())

    FakeTimer.instances[0].trigger()

    saved = secure_store.read_json(timers.TIMERS_STATE_PATH)
    assert saved == []


def test_persist_clears_on_cancel():
    tts = FakeTts()
    timers.handle_timer_set("5 minutes", Registry(), tts, log, Config())

    timers.handle_timer_cancel("", Registry(), tts, log, Config())

    saved = secure_store.read_json(timers.TIMERS_STATE_PATH)
    assert saved == []


def test_rehydrate_with_no_file_is_a_noop():
    tts = FakeTts()

    timers.rehydrate(tts, log)  # must not raise

    assert tts.said == []
    assert timers._active == {}


def test_rehydrate_with_malformed_file_is_a_noop():
    timers.TIMERS_STATE_PATH.write_text("not valid json {{{", encoding="utf-8")
    tts = FakeTts()

    timers.rehydrate(tts, log)  # must not raise

    assert tts.said == []


def test_rehydrate_reschedules_a_pending_timer():
    timers.TIMERS_STATE_PATH.write_text(
        json.dumps([{"label": "check the oven", "fires_at_wall": time.time() + 300}]),
        encoding="utf-8",
    )
    tts = FakeTts()

    timers.rehydrate(tts, log)

    assert tts.said == []  # not elapsed -- no catch-up message
    assert len(FakeTimer.instances) == 1
    assert 295 <= FakeTimer.instances[0].seconds <= 300
    assert len(timers._active) == 1


def test_rehydrate_announces_an_already_elapsed_timer():
    timers.TIMERS_STATE_PATH.write_text(
        json.dumps([{"label": "check the oven", "fires_at_wall": time.time() - 60}]),
        encoding="utf-8",
    )
    tts = FakeTts()

    timers.rehydrate(tts, log)

    assert tts.said == ["check the oven"]
    assert FakeTimer.instances == []  # nothing rescheduled -- it already fired
    assert timers._active == {}


def test_rehydrate_removes_elapsed_entry_from_disk():
    # Regression test: an elapsed entry that's only announced (not
    # rescheduled) must still be dropped from the persisted file, or
    # it gets re-announced on every future restart forever.
    timers.TIMERS_STATE_PATH.write_text(
        json.dumps([{"label": "check the oven", "fires_at_wall": time.time() - 60}]),
        encoding="utf-8",
    )

    timers.rehydrate(FakeTts(), log)

    saved = secure_store.read_json(timers.TIMERS_STATE_PATH)
    assert saved == []


def test_reminder_set_recurring_daily():
    tts = FakeTts()

    result = timers.handle_reminder_set("every day at 8am to take medicine", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert len(FakeTimer.instances) == 1
    assert "take medicine" in tts.said[-1]
    assert "every day at 8am" in tts.said[-1]


def test_reminder_set_recurring_weekdays():
    tts = FakeTts()

    timers.handle_reminder_set("every weekday at 9am check email", Registry(), tts, log, Config())

    assert "every weekday at 9am" in tts.said[-1]
    assert "check email" in tts.said[-1]


def test_recurring_reminder_reschedules_itself_after_firing():
    tts = FakeTts()
    timers.handle_reminder_set("every day at 8am to take medicine", Registry(), tts, log, Config())
    assert len(FakeTimer.instances) == 1

    FakeTimer.instances[0].trigger()

    # A second timer should now be scheduled for the next occurrence --
    # the entry was NOT simply removed like a one-shot timer.
    assert len(FakeTimer.instances) == 2
    assert len(timers._active) == 1
    assert "take medicine" in tts.said


def test_recurring_reminder_persists_recurrence_to_disk():
    tts = FakeTts()
    timers.handle_reminder_set("every day at 8am to take medicine", Registry(), tts, log, Config())

    saved = secure_store.read_json(timers.TIMERS_STATE_PATH)

    assert saved[0]["recurrence"] == {"schedule": "daily", "hour": 8, "minute": 0}


def test_rehydrate_reschedules_a_recurring_reminder():
    timers.TIMERS_STATE_PATH.write_text(
        json.dumps([{
            "label": "take medicine",
            "fires_at_wall": time.time() + 3600,
            "recurrence": {"schedule": "daily", "hour": 8, "minute": 0},
        }]),
        encoding="utf-8",
    )
    tts = FakeTts()

    timers.rehydrate(tts, log)

    assert len(FakeTimer.instances) == 1
    assert timers._active[list(timers._active.keys())[0]].recurrence == ("daily", 8, 0)


def test_rehydrate_elapsed_recurring_reminder_reschedules_next_occurrence():
    timers.TIMERS_STATE_PATH.write_text(
        json.dumps([{
            "label": "take medicine",
            "fires_at_wall": time.time() - 3600,  # missed while Ash was down
            "recurrence": {"schedule": "daily", "hour": 8, "minute": 0},
        }]),
        encoding="utf-8",
    )
    tts = FakeTts()

    timers.rehydrate(tts, log)

    assert tts.said == ["take medicine"]  # announced the missed one
    assert len(FakeTimer.instances) == 1  # and rescheduled for the next occurrence
    assert len(timers._active) == 1


def test_timer_list_describes_recurring_reminder():
    tts = FakeTts()
    timers.handle_reminder_set("every day at 8am to take medicine", Registry(), tts, log, Config())

    result = timers.handle_timer_list("", Registry(), tts, log, Config())

    assert result == HandlerResult()
    assert "take medicine" in tts.said[-1]
    assert "every day at 8am" in tts.said[-1]


def test_rehydrate_announces_elapsed_toast(monkeypatch):
    timers.TIMERS_STATE_PATH.write_text(
        json.dumps([{"label": "check the oven", "fires_at_wall": time.time() - 60}]),
        encoding="utf-8",
    )
    toasts = []
    monkeypatch.setattr(timers, "show_toast", lambda title, body, log=None: toasts.append((title, body)))

    timers.rehydrate(FakeTts(), log)

    assert toasts == [("Ash", "check the oven")]
