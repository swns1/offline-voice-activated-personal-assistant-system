import os
import subprocess

import pytest
import requests

import ash.actions.open_app as open_app_module
import ash.nlu.context as context_module
import ash.privacy.consent as consent_module
import ash.privacy.network_log as network_log_module
import ash.utils.ollama as ollama_module


def _build_all_allowed_state() -> bytes:
    """An encrypted privacy_state.json with every online feature allowed,
    built once per test run and copied into each test (encrypting it
    fresh for every test roughly doubled the suite's run time)."""
    import tempfile
    from pathlib import Path

    from ash.privacy import secure_store
    from ash.privacy.egress import FEATURES

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "privacy_state.json"
        secure_store.write_json(path, {
            "offline_mode": False,
            "consents": {key: {"granted": True, "at": "2026-01-01T00:00:00"} for key in FEATURES},
        })
        return path.read_bytes()


_all_allowed_state_bytes = _build_all_allowed_state()


@pytest.fixture(autouse=True)
def _no_real_side_effects(monkeypatch, tmp_path):
    """Safety net: no test may launch a real program, rescan this PC's
    real Start Menu/Steam library, make a real network request, probe a
    real Ollama server (the default ollama.enabled is "auto", which would
    otherwise make tests depend on whether Ollama happens to be running),
    or read/write your real privacy settings and network log. A test
    that needs any of these stubs it itself (its own monkeypatch runs
    after this one and wins).

    Privacy settings start as "every online feature allowed, online" so
    tests of what a feature *does* aren't interrupted by a consent
    question; tests of the consent flow itself reset that explicitly.

    Without this, a test that falls through to handle_open's
    rescan-on-miss path does a real scan, overwrites the real
    config/registry.auto.yaml, fuzzy-matches an actual installed app, and
    launches it -- which is exactly what used to happen."""
    def _blocked_process(*args, **kwargs):
        raise RuntimeError(f"Tests must not start real processes: {args!r}")

    def _blocked_rescan():
        raise RuntimeError("Tests must not rescan the real Start Menu/Steam library")

    monkeypatch.setattr(subprocess, "Popen", _blocked_process)
    monkeypatch.setattr(os, "startfile", _blocked_process, raising=False)
    monkeypatch.setattr(open_app_module, "refresh_registry_auto", _blocked_rescan)
    monkeypatch.setattr(ollama_module, "_probe", lambda host, model: ollama_module.NOT_RUNNING)
    monkeypatch.setattr(ollama_module, "_cache", {})

    def _blocked_network(self, method, url, *args, **kwargs):
        raise RuntimeError(f"Tests must not make real network requests: {method} {url}")

    monkeypatch.setattr(requests.Session, "request", _blocked_network)

    # In a subfolder, so tests that list their own tmp_path don't see it.
    state_dir = tmp_path / "_ash_privacy"
    state_dir.mkdir()
    state_path = state_dir / "privacy_state.json"
    state_path.write_bytes(_all_allowed_state_bytes)
    monkeypatch.setattr(consent_module, "PRIVACY_STATE_PATH", state_path)
    monkeypatch.setattr(network_log_module, "NETWORK_LOG_PATH", state_dir / "network_log.json")

    # Every other file Ash stores, too: even *reading* an old plain-text
    # file rewrites it encrypted (secure_store's migration), so a test
    # that merely asked "what data do you have" once rewrote the real
    # timers.json in your Ash data folder. Tests that need their own files
    # still patch these themselves.
    from ash.actions import diagnostics, memory, notes, privacy_rights, spotify, timers
    from ash.security import voice_gate
    from ash.utils import logging_setup, preferences
    monkeypatch.setattr(memory, "MEMORY_PATH", state_dir / "memory.json")
    monkeypatch.setattr(timers, "TIMERS_STATE_PATH", state_dir / "timers.json")
    monkeypatch.setattr(voice_gate, "VOICEPRINT_PATH", state_dir / "voiceprint.json")
    monkeypatch.setattr(notes, "NOTES_PATH", state_dir / "notes.json")
    monkeypatch.setattr(preferences, "PREFERENCES_PATH", state_dir / "preferences.json")
    monkeypatch.setattr(spotify, "_CACHE_PATH", state_dir / ".spotify_cache")
    monkeypatch.setattr(diagnostics, "SPOTIFY_TOKEN_PATH", state_dir / ".spotify_cache")
    monkeypatch.setattr(logging_setup, "LOG_DIR", state_dir / "logs")
    monkeypatch.setattr(privacy_rights, "_documents_dir", lambda: state_dir / "Documents")

    # Nor change real PC settings or save into your real folders.
    from ash.actions import device

    def _blocked_setting(*args, **kwargs):
        raise RuntimeError("Tests must not change real Windows settings")

    monkeypatch.setattr(device, "_pictures_dir", lambda: state_dir / "Pictures")
    from ash.actions import files
    monkeypatch.setattr(files, "_downloads_dir", lambda: state_dir / "Downloads")
    from ash import setup_models
    monkeypatch.setattr(setup_models, "MODELS_DIR", state_dir / "models")
    monkeypatch.setattr(device, "_set_theme", _blocked_setting)
    monkeypatch.setattr(device, "set_brightness", _blocked_setting)

    # Nor reach your real Outlook (calendar, inbox, address book, sending),
    # or search your real files.
    import win32com.client

    real_dispatch = win32com.client.Dispatch

    def _no_outlook(prog_id, *args, **kwargs):
        if str(prog_id).lower().startswith("outlook."):
            raise RuntimeError("Tests must not use the real Outlook")
        if str(prog_id).lower().startswith("adodb."):
            raise RuntimeError("Tests must not query the real Windows Search index")
        return real_dispatch(prog_id, *args, **kwargs)

    monkeypatch.setattr(win32com.client, "Dispatch", _no_outlook)

    # Nor write to the real Windows registry (e.g. the "start at sign-in"
    # entry, which the Settings tab's save applies). Reading is fine.
    # tests/test_autostart.py swaps in its own fake functions.
    import winreg

    def _blocked_registry_write(*args, **kwargs):
        raise RuntimeError("Tests must not write to the real Windows registry")

    for name in ("CreateKey", "CreateKeyEx", "SetValue", "SetValueEx", "DeleteKey", "DeleteKeyEx", "DeleteValue"):
        monkeypatch.setattr(winreg, name, _blocked_registry_write)


@pytest.fixture(autouse=True)
def _reset_recent_context():
    """ash.nlu.context tracks last-opened-app/search/track as shared
    module state, touched by tests across several files (open_app,
    search, spotify, context, dispatcher) -- reset it before every test
    so none of them leak state into each other."""
    context_module._context = context_module._RecentContext()
    yield
