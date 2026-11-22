import os
import subprocess

import pytest

import ash.actions.open_app as open_app_module
import ash.nlu.context as context_module
import ash.utils.ollama as ollama_module


@pytest.fixture(autouse=True)
def _no_real_side_effects(monkeypatch):
    """Safety net: no test may launch a real program, rescan this PC's
    real Start Menu/Steam library, or probe a real Ollama server (the
    default ollama.enabled is "auto", which would otherwise make tests
    depend on whether Ollama happens to be running). A test that needs
    any of these stubs it itself (its own monkeypatch runs after this
    one and wins).

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


@pytest.fixture(autouse=True)
def _reset_recent_context():
    """ash.nlu.context tracks last-opened-app/search/track as shared
    module state, touched by tests across several files (open_app,
    search, spotify, context, dispatcher) -- reset it before every test
    so none of them leak state into each other."""
    context_module._context = context_module._RecentContext()
    yield
