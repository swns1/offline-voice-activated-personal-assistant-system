"""ash.privacy.secure_store: personal data is encrypted at rest with
Windows DPAPI. These tests use real DPAPI -- it has no side effects
beyond the bytes it returns, and it's the behavior that matters."""
import json

import numpy as np
import pytest

from ash.actions import memory, spotify
from ash.privacy import secure_store
from ash.security import voice_gate


def test_round_trip(tmp_path):
    path = tmp_path / "data.json"
    secure_store.write_json(path, {"facts": ["I'm vegetarian"], "n": 3})
    assert secure_store.read_json(path) == {"facts": ["I'm vegetarian"], "n": 3}


def test_file_on_disk_is_not_readable_plaintext(tmp_path):
    path = tmp_path / "data.json"
    secure_store.write_json(path, {"secret": "my dog's name is Rex"})

    raw = path.read_bytes()
    assert b"Rex" not in raw
    assert b"secret" not in raw
    assert secure_store.is_encrypted(path)
    with pytest.raises(ValueError):
        json.loads(raw)


def test_missing_file_returns_default(tmp_path):
    assert secure_store.read_json(tmp_path / "nope.json", default=[]) == []
    assert secure_store.read_json(tmp_path / "nope.json") is None


def test_legacy_plaintext_file_is_read_and_migrated(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text(json.dumps({"facts": ["old fact"]}), encoding="utf-8")
    assert not secure_store.is_encrypted(path)

    assert secure_store.read_json(path) == {"facts": ["old fact"]}

    assert secure_store.is_encrypted(path)  # rewritten encrypted in the same call
    assert b"old fact" not in path.read_bytes()
    assert secure_store.read_json(path) == {"facts": ["old fact"]}


def test_corrupt_encrypted_file_raises_value_error(tmp_path):
    path = tmp_path / "data.json"
    secure_store.write_json(path, {"a": 1})
    path.write_bytes(path.read_bytes()[:-8] + b"tampered")

    with pytest.raises(ValueError):
        secure_store.read_json(path)


def test_garbage_plaintext_raises_value_error(tmp_path):
    path = tmp_path / "data.json"
    path.write_text("not valid json {{{", encoding="utf-8")
    with pytest.raises(ValueError):
        secure_store.read_json(path)


def test_write_leaves_no_temp_file_behind(tmp_path):
    secure_store.write_json(tmp_path / "data.json", [1, 2, 3])
    assert [p.name for p in tmp_path.iterdir() if p.is_file()] == ["data.json"]


def test_write_creates_missing_parent_folder(tmp_path):
    path = tmp_path / "nested" / "Ash" / "data.json"
    secure_store.write_json(path, {"ok": True})
    assert secure_store.read_json(path) == {"ok": True}


# --- each kind of personal data really ends up encrypted -------------------

class _FakeTts:
    def say(self, text):
        pass


def test_remembered_facts_are_stored_encrypted(monkeypatch, tmp_path):
    import logging
    from ash.config import Config
    from ash.registry.schema import Registry

    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "memory.json")
    memory.handle_memory_remember("my dog's name is Rex", Registry(), _FakeTts(), logging.getLogger("t"), Config())

    assert secure_store.is_encrypted(memory.MEMORY_PATH)
    assert b"Rex" not in memory.MEMORY_PATH.read_bytes()


def test_voiceprint_is_stored_encrypted(monkeypatch, tmp_path):
    monkeypatch.setattr(voice_gate, "VOICEPRINT_PATH", tmp_path / "voiceprint.json")
    rng = np.random.default_rng(0)
    assert voice_gate.enroll(rng.normal(0, 0.1, 16000 * 2).astype(np.float32))

    assert secure_store.is_encrypted(voice_gate.VOICEPRINT_PATH)
    assert b"mfcc_mean" not in voice_gate.VOICEPRINT_PATH.read_bytes()


def test_spotify_token_cache_is_encrypted_and_migrates(tmp_path):
    path = tmp_path / ".spotify_cache"
    path.write_text(json.dumps({"access_token": "abc123"}), encoding="utf-8")  # spotipy's old plain cache
    cache = spotify._EncryptedTokenCache(path)

    assert cache.get_cached_token() == {"access_token": "abc123"}
    assert secure_store.is_encrypted(path)

    cache.save_token_to_cache({"access_token": "new-token"})
    assert b"new-token" not in path.read_bytes()
    assert cache.get_cached_token() == {"access_token": "new-token"}


def test_spotify_unreadable_cache_means_not_authorized(tmp_path):
    path = tmp_path / ".spotify_cache"
    path.write_text("garbage", encoding="utf-8")
    assert spotify._EncryptedTokenCache(path).get_cached_token() is None
