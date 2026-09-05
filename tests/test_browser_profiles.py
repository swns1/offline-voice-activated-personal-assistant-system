import json

from ash.launchers import browser_profiles


def _fake_local_state(tmp_path, profiles: dict[str, str]) -> None:
    """profiles: {internal_directory_key: display_name}"""
    path = tmp_path / "Local State"
    info_cache = {key: {"name": name} for key, name in profiles.items()}
    path.write_text(json.dumps({"profile": {"info_cache": info_cache}}), encoding="utf-8")


def test_list_profiles_maps_display_name_to_internal_key(tmp_path, monkeypatch):
    _fake_local_state(tmp_path, {"Default": "Person 1", "Profile 1": "Work"})
    monkeypatch.setitem(browser_profiles._LOCAL_STATE_PATHS, "chrome", str(tmp_path / "Local State"))

    profiles = browser_profiles.list_profiles("chrome")

    assert profiles == {"person 1": "Default", "work": "Profile 1"}


def test_resolve_profile_exact_match(tmp_path, monkeypatch):
    _fake_local_state(tmp_path, {"Profile 1": "Work"})
    monkeypatch.setitem(browser_profiles._LOCAL_STATE_PATHS, "chrome", str(tmp_path / "Local State"))

    assert browser_profiles.resolve_profile("chrome", "Work") == "Profile 1"


def test_resolve_profile_fuzzy_match(tmp_path, monkeypatch):
    _fake_local_state(tmp_path, {"Profile 1": "Work"})
    monkeypatch.setitem(browser_profiles._LOCAL_STATE_PATHS, "chrome", str(tmp_path / "Local State"))

    assert browser_profiles.resolve_profile("chrome", "work profile") == "Profile 1"


def test_resolve_profile_no_match_returns_none(tmp_path, monkeypatch):
    _fake_local_state(tmp_path, {"Profile 1": "Work"})
    monkeypatch.setitem(browser_profiles._LOCAL_STATE_PATHS, "chrome", str(tmp_path / "Local State"))

    assert browser_profiles.resolve_profile("chrome", "something totally unrelated") is None


def test_missing_local_state_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setitem(browser_profiles._LOCAL_STATE_PATHS, "chrome", str(tmp_path / "does_not_exist"))

    assert browser_profiles.list_profiles("chrome") == {}
    assert browser_profiles.resolve_profile("chrome", "Work") is None


def test_malformed_local_state_file_returns_empty(tmp_path, monkeypatch):
    path = tmp_path / "Local State"
    path.write_text("not valid json {{{", encoding="utf-8")
    monkeypatch.setitem(browser_profiles._LOCAL_STATE_PATHS, "chrome", str(path))

    assert browser_profiles.list_profiles("chrome") == {}


def test_unknown_browser_returns_empty():
    assert browser_profiles.list_profiles("firefox") == {}
