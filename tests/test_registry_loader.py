import pytest

from ash.registry.loader import load_registry


def _no_auto(tmp_path):
    return tmp_path / "does_not_exist.auto.yaml"


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

    registry = load_registry(registry_file, auto_path=_no_auto(tmp_path))

    assert len(registry.apps) == 1
    assert registry.apps[0].id == "notepad"
    assert registry.apps[0].names == ["notepad", "note pad"]
    assert "search" in registry.intents


def test_missing_file_yields_empty_registry(tmp_path):
    registry = load_registry(
        tmp_path / "does_not_exist.yaml", auto_path=tmp_path / "does_not_exist.auto.yaml"
    )
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
        load_registry(registry_file, auto_path=_no_auto(tmp_path))


def test_auto_apps_are_merged_in(tmp_path):
    manual_path = tmp_path / "registry.yaml"
    manual_path.write_text(
        'apps:\n  - id: notepad\n    names: ["notepad"]\n    launch: {type: exe, target: "notepad.exe"}\n',
        encoding="utf-8",
    )
    auto_path = tmp_path / "registry.auto.yaml"
    auto_path.write_text(
        'apps:\n  - id: discord\n    names: ["discord"]\n    launch: {type: exe, target: "discord.exe"}\n'
        '    source: start_menu\n',
        encoding="utf-8",
    )

    registry = load_registry(manual_path, auto_path=auto_path)

    ids = {entry.id for entry in registry.apps}
    assert ids == {"notepad", "discord"}


def test_manual_wins_over_auto_on_id_collision(tmp_path):
    manual_path = tmp_path / "registry.yaml"
    manual_path.write_text(
        'apps:\n  - id: steam_client\n    names: ["steam"]\n'
        '    launch: {type: uri, protocol: steam, uri_template: "steam://open/main"}\n',
        encoding="utf-8",
    )
    auto_path = tmp_path / "registry.auto.yaml"
    auto_path.write_text(
        'apps:\n  - id: steam_client\n    names: ["steam"]\n'
        '    launch: {type: exe, target: "steam.exe"}\n    source: start_menu\n',
        encoding="utf-8",
    )

    registry = load_registry(manual_path, auto_path=auto_path)

    assert len(registry.apps) == 1
    assert registry.apps[0].launch["type"] == "uri"


def test_manual_wins_over_auto_on_name_collision_with_different_id(tmp_path):
    manual_path = tmp_path / "registry.yaml"
    manual_path.write_text(
        'apps:\n  - id: steam_client\n    names: ["steam"]\n'
        '    launch: {type: uri, protocol: steam, uri_template: "steam://open/main"}\n',
        encoding="utf-8",
    )
    # Auto-discovered entry has a different id (from the .lnk filename) but
    # the same spoken name -- must still be dropped in favor of manual.
    auto_path = tmp_path / "registry.auto.yaml"
    auto_path.write_text(
        'apps:\n  - id: steam\n    names: ["steam"]\n'
        '    launch: {type: exe, target: "steam.exe"}\n    source: start_menu\n',
        encoding="utf-8",
    )

    registry = load_registry(manual_path, auto_path=auto_path)

    assert len(registry.apps) == 1
    assert registry.apps[0].id == "steam_client"


def test_missing_auto_file_is_fine(tmp_path):
    manual_path = tmp_path / "registry.yaml"
    manual_path.write_text(
        'apps:\n  - id: notepad\n    names: ["notepad"]\n    launch: {type: exe, target: "notepad.exe"}\n',
        encoding="utf-8",
    )

    registry = load_registry(manual_path, auto_path=tmp_path / "does_not_exist.auto.yaml")

    assert len(registry.apps) == 1
