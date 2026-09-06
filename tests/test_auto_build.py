import yaml

from ash.registry import auto_build


def test_build_registry_auto_dedupes_start_menu_against_steam(monkeypatch):
    monkeypatch.setattr(auto_build, "scan_steam_library", lambda: [
        {"id": "steam_1", "names": ["elden ring"], "launch": {"type": "uri"}, "source": "steam"},
    ])
    monkeypatch.setattr(auto_build, "scan_start_menu", lambda: [
        {"id": "start_elden_ring", "names": ["elden ring"], "launch": {"type": "exe"}, "source": "start_menu"},
        {"id": "start_notepad", "names": ["notepad"], "launch": {"type": "exe"}, "source": "start_menu"},
    ])

    apps = auto_build.build_registry_auto()

    assert [a["id"] for a in apps] == ["steam_1", "start_notepad"]


def test_build_registry_auto_empty_when_nothing_found(monkeypatch):
    monkeypatch.setattr(auto_build, "scan_steam_library", lambda: [])
    monkeypatch.setattr(auto_build, "scan_start_menu", lambda: [])

    assert auto_build.build_registry_auto() == []


def test_refresh_registry_auto_writes_yaml_and_returns_count(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_build, "scan_steam_library", lambda: [
        {"id": "steam_1", "names": ["elden ring"], "launch": {"type": "uri"}, "source": "steam"},
    ])
    monkeypatch.setattr(auto_build, "scan_start_menu", lambda: [])
    out_path = tmp_path / "registry.auto.yaml"
    monkeypatch.setattr(auto_build, "REGISTRY_AUTO_PATH", out_path)

    count = auto_build.refresh_registry_auto()

    assert count == 1
    written = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert written["apps"][0]["id"] == "steam_1"
