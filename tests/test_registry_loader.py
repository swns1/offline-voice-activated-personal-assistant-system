import pytest

from ash.registry.loader import load_registry


def test_loads_apps_and_intents(tmp_path):
    registry_file = tmp_path / "registry.yaml"
    registry_file.write_text(
        """
apps:
  - id: notepad
    names: ["notepad", "note pad"]
    launch:
      type: exe
      target: "%WINDIR%\\\\System32\\\\notepad.exe"
intents:
  search:
    verbs: ["search"]
    launch:
      type: browser_search
      engine_url: "https://www.google.com/search?q={query}"
""",
        encoding="utf-8",
    )

    registry = load_registry(registry_file)

    assert len(registry.apps) == 1
    assert registry.apps[0].id == "notepad"
    assert registry.apps[0].names == ["notepad", "note pad"]
    assert "search" in registry.intents


def test_missing_file_yields_empty_registry(tmp_path):
    registry = load_registry(tmp_path / "does_not_exist.yaml")
    assert registry.apps == []
    assert registry.intents == {}


def test_launch_without_type_is_rejected(tmp_path):
    registry_file = tmp_path / "registry.yaml"
    registry_file.write_text(
        """
apps:
  - id: broken
    names: ["broken"]
    launch:
      target: "somewhere.exe"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_registry(registry_file)
