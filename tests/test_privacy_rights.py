"""Your data rights (ash/actions/privacy_rights.py), driven by the data
inventory (ash/privacy/inventory.py)."""
import json
import logging
from logging.handlers import TimedRotatingFileHandler

import pytest

import ash.utils.paths as paths
from ash.actions import memory, privacy_rights, spotify, timers
from ash.config import Config
from ash.nlu import context
from ash.privacy import consent, inventory, network_log, secure_store
from ash.registry.schema import Registry
from ash.security import voice_gate
from ash.utils import logging_setup

log = logging.getLogger("test")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


@pytest.fixture
def app_data(monkeypatch, tmp_path):
    """A private %LOCALAPPDATA%\\Ash for each test, starting empty
    (conftest already pre-fills privacy choices -- removed here)."""
    root = tmp_path / "Ash"
    root.mkdir()
    (root / "logs").mkdir()
    monkeypatch.setattr(memory, "MEMORY_PATH", root / "memory.json")
    monkeypatch.setattr(timers, "TIMERS_STATE_PATH", root / "timers.json")
    monkeypatch.setattr(voice_gate, "VOICEPRINT_PATH", root / "voiceprint.json")
    monkeypatch.setattr(spotify, "_CACHE_PATH", root / ".spotify_cache")
    monkeypatch.setattr(consent, "PRIVACY_STATE_PATH", root / "privacy_state.json")
    monkeypatch.setattr(network_log, "NETWORK_LOG_PATH", root / "network_log.json")
    monkeypatch.setattr(logging_setup, "LOG_DIR", root / "logs")
    monkeypatch.setattr(paths, "REGISTRY_AUTO_PATH", tmp_path / "config" / "registry.auto.yaml")
    monkeypatch.setattr(privacy_rights, "_documents_dir", lambda: tmp_path / "Documents")
    return root


def _fill(app_data, tmp_path):
    """Store one of everything."""
    secure_store.write_json(memory.MEMORY_PATH, {"facts": ["I'm vegetarian", "my dog is Rex"]})
    secure_store.write_json(timers.TIMERS_STATE_PATH, [{"label": "take medicine", "fires_at_wall": 9e9}])
    secure_store.write_json(voice_gate.VOICEPRINT_PATH, {"mfcc_mean": [0.12345, 0.6789]})
    secure_store.write_json(spotify._CACHE_PATH, {"access_token": "SECRET-TOKEN"})
    consent.grant("web_search")
    network_log.record("web_search", "web search", "DuckDuckGo", "api.duckduckgo.com", "the words you search for")
    (app_data / "logs" / "ash.log").write_text("a log line\n", encoding="utf-8")
    apps = tmp_path / "config" / "registry.auto.yaml"
    apps.parent.mkdir()
    apps.write_text("apps: []\n", encoding="utf-8")


# --- the inventory is complete ------------------------------------------------

def test_every_file_ash_stores_is_in_the_inventory():
    """A new *_PATH under %LOCALAPPDATA%\\Ash must be added to the
    inventory, or "what data do you have" / export / delete would miss it."""
    stored_paths = {
        value for name, value in vars(paths).items()
        if name.endswith("_PATH") and paths.APP_DATA_DIR in value.parents
    }
    listed = set()
    for item in inventory.INVENTORY:
        listed.update(p.name for p in item.paths())
    missing = sorted(p.name for p in stored_paths if p.name not in listed)
    assert missing == [], f"Add these to ash/privacy/inventory.py: {missing}"
    # The log folder (paths.LOG_DIR) is covered by the "logs" item.
    assert "logs" in {item.key for item in inventory.INVENTORY}


def test_every_item_says_why_and_for_how_long():
    for item in inventory.INVENTORY:
        assert item.purpose and item.kept, item.key
        if not item.exportable:
            assert item.export_note, f"{item.key}: say why it isn't in the export"


# --- what data do you have ---------------------------------------------------------

def test_nothing_stored(app_data):
    tts = FakeTts()
    privacy_rights.handle_data_inventory("", Registry(), tts, log, Config())
    assert tts.said == ["I'm not keeping anything about you on this PC right now."]


def test_lists_what_is_stored_with_counts(app_data, tmp_path):
    _fill(app_data, tmp_path)
    tts = FakeTts()

    privacy_rights.handle_data_inventory("", Registry(), tts, log, Config())

    reply = tts.said[-1]
    assert "2 remembered facts" in reply
    assert "1 timer or reminder" in reply
    assert "your voiceprint" in reply
    assert "a log of 1 time I went online" in reply
    assert "encrypted except the troubleshooting logs, which don't include what you say" in reply
    assert "installed apps" not in reply  # not about you
    assert "export my data" in reply and "delete all my data" in reply


# --- export my data ------------------------------------------------------------------

def test_export_asks_first_and_warns_the_copy_is_not_encrypted(app_data, tmp_path):
    _fill(app_data, tmp_path)
    result = privacy_rights.handle_export("", Registry(), FakeTts(), log, Config())

    assert result.done is False
    assert "won't be encrypted" in result.question
    assert not (tmp_path / "Documents").exists()  # nothing written before you agree


def test_export_writes_a_readable_copy(app_data, tmp_path):
    _fill(app_data, tmp_path)
    tts = FakeTts()
    privacy_rights.handle_export("", Registry(), tts, log, Config()).resume("Yes.")

    [export_file] = list((tmp_path / "Documents").glob("Ash data export *.json"))
    data = json.loads(export_file.read_text(encoding="utf-8"))
    items = {i["name"]: i for i in data["items"]}

    assert items["remembered facts"]["contents"] == {"facts": ["I'm vegetarian", "my dog is Rex"]}
    assert items["timers and reminders"]["contents"][0]["label"] == "take medicine"
    assert items["your privacy choices"]["contents"]["consents"]["web_search"]["granted"] is True
    assert items["the network log"]["contents"][0]["service"] == "DuckDuckGo"
    assert items["remembered facts"]["purpose"] and items["remembered facts"]["kept"]
    assert "Documents" in tts.said[-1]


def test_export_never_copies_secrets_or_biometrics(app_data, tmp_path):
    _fill(app_data, tmp_path)
    privacy_rights.handle_export("", Registry(), FakeTts(), log, Config()).resume("yes")

    raw = next((tmp_path / "Documents").glob("*.json")).read_text(encoding="utf-8")
    assert "SECRET-TOKEN" not in raw
    assert "0.12345" not in raw
    data = json.loads(raw)
    voiceprint = next(i for i in data["items"] if i["name"] == "your voiceprint")
    assert voiceprint["stored"] is True and "note" in voiceprint and "contents" not in voiceprint


def test_export_declined_writes_nothing(app_data, tmp_path):
    _fill(app_data, tmp_path)
    tts = FakeTts()
    privacy_rights.handle_export("", Registry(), tts, log, Config()).resume("no")
    assert not (tmp_path / "Documents").exists()
    assert tts.said[-1] == "Okay, I won't export anything."


# --- delete my voiceprint ---------------------------------------------------------------

def test_delete_voiceprint_when_none_saved(app_data):
    tts = FakeTts()
    result = privacy_rights.handle_delete_voiceprint("", Registry(), tts, log, Config())
    assert result.done is True
    assert tts.said == ["You don't have a voiceprint saved."]


def test_delete_voiceprint_explains_then_deletes(app_data, tmp_path):
    _fill(app_data, tmp_path)
    config = Config()
    config.security.voice_gate_enabled = True

    result = privacy_rights.handle_delete_voiceprint("", Registry(), FakeTts(), log, config)
    assert "plain yes" in result.question  # what you lose: the voice check
    result.resume("yes")

    assert not voice_gate.VOICEPRINT_PATH.exists()
    assert memory.MEMORY_PATH.exists()  # nothing else touched


# --- delete all my data --------------------------------------------------------------------

def test_delete_all_lists_what_will_be_lost_and_asks(app_data, tmp_path):
    _fill(app_data, tmp_path)
    result = privacy_rights.handle_delete_all("", Registry(), FakeTts(), log, Config())

    assert result.done is False
    for name in ("remembered facts", "your voiceprint", "your Spotify login", "the network log"):
        assert name in result.question
    assert "can't be undone" in result.question


def test_delete_all_declined_keeps_everything(app_data, tmp_path):
    _fill(app_data, tmp_path)
    before = sorted(p.name for p in app_data.rglob("*") if p.is_file())

    privacy_rights.handle_delete_all("", Registry(), FakeTts(), log, Config()).resume("no")

    assert sorted(p.name for p in app_data.rglob("*") if p.is_file()) == before


def test_delete_all_leaves_nothing_behind(app_data, tmp_path):
    _fill(app_data, tmp_path)
    # A real open log file, like Ash's own: Windows won't delete it unless closed first.
    file_logger = logging.getLogger("ash.test-delete-all")
    handler = TimedRotatingFileHandler(app_data / "logs" / "ash.log", when="midnight", encoding="utf-8")
    file_logger.addHandler(handler)
    file_logger.propagate = False
    file_logger.warning("open log file")
    context.remember_app("discord")
    tts = FakeTts()
    try:
        privacy_rights.handle_delete_all("", Registry(), tts, file_logger, Config()).resume("Yes.")
    finally:
        file_logger.removeHandler(handler)
        handler.close()

    assert [p for p in app_data.rglob("*") if p.is_file()] == []
    assert (tmp_path / "config" / "registry.auto.yaml").exists()  # not about you; rebuilt each start
    assert consent.status("web_search") == consent.UNASKED      # online features ask again
    assert context.resolve_target("close_app", "it") == "it"     # "it" no longer means discord
    assert tts.said[-1] == "Done. Everything I kept about you on this PC has been deleted."


def test_delete_all_stops_pending_reminders(app_data, tmp_path, monkeypatch):
    cancelled = []
    monkeypatch.setattr(timers, "cancel_all", lambda persist=True: cancelled.append(persist) or 0)
    _fill(app_data, tmp_path)

    privacy_rights.handle_delete_all("", Registry(), FakeTts(), log, Config()).resume("yes")

    assert cancelled == [False]  # cancelled without rewriting the file it then deletes


def test_delete_all_with_nothing_stored(app_data):
    tts = FakeTts()
    result = privacy_rights.handle_delete_all("", Registry(), tts, log, Config())
    assert result.done is True
    assert "nothing to delete" in tts.said[-1]


def test_privacy_doc_covers_every_stored_item_and_online_feature():
    """docs/PRIVACY.md is written by hand -- keep it in step with the code."""
    from pathlib import Path

    from ash.privacy.egress import FEATURES

    doc = (Path(__file__).resolve().parents[1] / "docs" / "PRIVACY.md").read_text(encoding="utf-8")
    missing = [item.name for item in inventory.INVENTORY if item.name not in doc]
    missing += [f"{f.name} ({f.service})" for f in FEATURES.values() if f.name not in doc or f.service not in doc]
    assert missing == [], f"Add these to docs/PRIVACY.md: {missing}"


def test_tests_never_touch_your_real_data_folder():
    """Every stored file is redirected away from your real Ash data
    folder during tests (tests/conftest.py). A new kind of stored data
    must be added there as well as to the inventory."""
    import ash.utils.paths as real_paths

    leaking = [
        f"{item.key}: {path}"
        for item in inventory.INVENTORY if item.key != "installed_apps"
        for path in item.paths()
        if real_paths.APP_DATA_DIR in path.parents or path.parent == real_paths.APP_DATA_DIR
    ]
    assert leaking == [], f"Redirect these in tests/conftest.py: {leaking}"
