from ash.registry.steam_scan import scan_steam_library


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_scans_single_library_no_libraryfolders_vdf(tmp_path):
    steam_path = tmp_path / "steam"
    _write(
        steam_path / "steamapps" / "appmanifest_1245620.acf",
        '"AppState"\n{\n\t"appid"\t\t"1245620"\n\t"name"\t\t"ELDEN RING"\n}\n',
    )

    entries = scan_steam_library(steam_path)

    assert len(entries) == 1
    assert entries[0]["id"] == "steam_1245620"
    assert entries[0]["names"] == ["elden ring"]
    assert entries[0]["launch"]["appid"] == "1245620"
    assert entries[0]["launch"]["uri_template"] == "steam://rungameid/{appid}"


def test_follows_libraryfolders_vdf_to_additional_drives(tmp_path):
    steam_path = tmp_path / "steam"
    other_library = tmp_path / "games_on_d"
    _write(
        steam_path / "steamapps" / "libraryfolders.vdf",
        '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n}\n' % str(other_library).replace("\\", "\\\\"),  # noqa: UP031
    )
    _write(
        other_library / "steamapps" / "appmanifest_945360.acf",
        '"AppState"\n{\n\t"appid"\t\t"945360"\n\t"name"\t\t"Among Us"\n}\n',
    )

    entries = scan_steam_library(steam_path)

    assert len(entries) == 1
    assert entries[0]["id"] == "steam_945360"


def test_filters_non_game_pseudo_apps(tmp_path):
    steam_path = tmp_path / "steam"
    _write(
        steam_path / "steamapps" / "appmanifest_228980.acf",
        '"AppState"\n{\n\t"appid"\t\t"228980"\n\t"name"\t\t"Steamworks Common Redistributables"\n}\n',
    )

    entries = scan_steam_library(steam_path)

    assert entries == []


def test_no_steam_installed_returns_empty(tmp_path):
    entries = scan_steam_library(tmp_path / "does_not_exist")
    assert entries == []


def test_malformed_manifest_is_skipped_not_raised(tmp_path):
    steam_path = tmp_path / "steam"
    _write(steam_path / "steamapps" / "appmanifest_1.acf", "not valid vdf {{{")

    entries = scan_steam_library(steam_path)

    assert entries == []
