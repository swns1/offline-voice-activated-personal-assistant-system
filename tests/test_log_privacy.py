"""What may end up in Ash's log files (ash/privacy/redact.py) and how
long log files are kept (ash/utils/logging_setup.py)."""
import logging
import os
import time
from logging.handlers import TimedRotatingFileHandler

import pytest
from pydantic import ValidationError

from ash.actions import desktop_control, memory, search
from ash.config import Config, PrivacyConfig
from ash.privacy import redact
from ash.registry.schema import Registry
from ash.utils import logging_setup

log = logging.getLogger("ash.test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


@pytest.fixture
def content_logging(monkeypatch):
    def _set(enabled: bool):
        monkeypatch.setattr(redact, "_log_content", enabled)
    return _set


def _all_log_text(caplog) -> str:
    return "\n".join(r.getMessage() for r in caplog.records)


# --- redact.said -----------------------------------------------------------

def test_said_hides_content_by_default():
    assert redact.said("remind me to take my medicine") == "<6 words hidden>"
    assert redact.said("hello") == "<1 word hidden>"


def test_said_shows_content_when_enabled(content_logging):
    content_logging(True)
    assert redact.said("take my medicine") == "'take my medicine'"


def test_privacy_defaults():
    privacy = Config().privacy
    assert privacy.log_transcripts is False
    assert privacy.log_retention_days == 7


def test_retention_must_be_at_least_one_day():
    with pytest.raises(ValidationError):
        PrivacyConfig(log_retention_days=0)


# --- what handlers actually log --------------------------------------------

def test_search_query_is_not_logged_by_default(monkeypatch, caplog):
    monkeypatch.setattr(search, "_query_duckduckgo", lambda query: None)
    caplog.set_level(logging.INFO)

    search.handle_search("symptoms of diabetes", Registry(), FakeTts(), log, Config())

    assert "diabetes" not in _all_log_text(caplog)
    assert "hidden" in _all_log_text(caplog)


def test_remembered_facts_are_never_logged_even_with_transcripts_on(monkeypatch, tmp_path, caplog, content_logging):
    content_logging(True)
    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "memory.json")
    caplog.set_level(logging.INFO)

    memory.handle_memory_remember("my PIN is 4321", Registry(), FakeTts(), log, Config())
    memory.handle_memory_forget("my PIN is 4321", Registry(), FakeTts(), log, Config())

    assert "4321" not in _all_log_text(caplog)


def test_typed_text_is_never_logged_even_with_transcripts_on(monkeypatch, caplog, content_logging):
    content_logging(True)
    monkeypatch.setattr(desktop_control.pyautogui, "write", lambda text: None)
    config = Config()
    config.desktop_control.enabled = True
    caplog.set_level(logging.INFO)

    result = desktop_control.handle_screen_type("hunter2", Registry(), FakeTts(), log, config)
    result.resume("yes")

    assert "hunter2" not in _all_log_text(caplog)
    assert "Typed 7 characters" in _all_log_text(caplog)


# --- log retention ---------------------------------------------------------

def _make_log(path, age_days, now):
    path.write_text("old log line\n", encoding="utf-8")
    stamp = now - age_days * 24 * 60 * 60
    os.utime(path, (stamp, stamp))


def test_retention_deletes_only_logs_older_than_the_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(logging_setup, "LOG_DIR", tmp_path)
    now = time.time()
    _make_log(tmp_path / "ash.log", 0, now)
    _make_log(tmp_path / "ash.log.2026-11-20", 2, now)
    _make_log(tmp_path / "ash.log.1", 30, now)            # left behind by the old size-based rotation
    _make_log(tmp_path / "ash.log.2026-10-01", 52, now)
    (tmp_path / "unrelated.txt").write_text("keep me", encoding="utf-8")
    os.utime(tmp_path / "unrelated.txt", (now - 99 * 86400, now - 99 * 86400))

    deleted = logging_setup.apply_log_retention(7, logging.getLogger("ash.retention-test"), now=now)

    assert sorted(deleted) == ["ash.log.1", "ash.log.2026-10-01"]
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == ["ash.log", "ash.log.2026-11-20", "unrelated.txt"]


def test_retention_deletes_a_stale_current_log_too(monkeypatch, tmp_path):
    monkeypatch.setattr(logging_setup, "LOG_DIR", tmp_path)
    now = time.time()
    _make_log(tmp_path / "ash.log", 10, now)  # Ash hasn't run for 10 days

    deleted = logging_setup.apply_log_retention(7, logging.getLogger("ash.retention-test2"), now=now)

    assert deleted == ["ash.log"]


def test_retention_sets_how_many_daily_files_the_handler_keeps(tmp_path):
    logger = logging.getLogger("ash.retention-test3")
    handler = TimedRotatingFileHandler(tmp_path / "x.log", when="midnight", backupCount=7, delay=True)
    logger.addHandler(handler)
    try:
        logging_setup.apply_log_retention(3, logger)
        assert handler.backupCount == 3
    finally:
        logger.removeHandler(handler)
        handler.close()
