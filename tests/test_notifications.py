import logging

from ash.utils import notifications

log = logging.getLogger("test")


def test_show_toast_calls_notify(monkeypatch):
    calls = []
    monkeypatch.setattr(notifications, "notify", lambda title, body: calls.append((title, body)))

    notifications.show_toast("Ash", "Time's up.", log)

    assert calls == [("Ash", "Time's up.")]


def test_show_toast_swallows_exceptions(monkeypatch):
    def boom(title, body):
        raise RuntimeError("no notification service")
    monkeypatch.setattr(notifications, "notify", boom)

    notifications.show_toast("Ash", "Time's up.", log)  # must not raise


def test_show_toast_without_logger_still_swallows_exceptions(monkeypatch):
    def boom(title, body):
        raise RuntimeError("no notification service")
    monkeypatch.setattr(notifications, "notify", boom)

    notifications.show_toast("Ash", "Time's up.")  # log=None, must not raise
