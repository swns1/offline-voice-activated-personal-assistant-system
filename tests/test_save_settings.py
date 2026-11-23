"""save_settings() (ash/config.py): the Settings tab writes config.yaml
without losing your comments or other settings."""
import pydantic
import pytest

from ash.config import load_config, save_settings
from ash.utils.paths import CONFIG_PATH


def test_changes_only_what_you_changed_and_keeps_comments(tmp_path):
    path = tmp_path / "config.yaml"
    original = CONFIG_PATH.read_text(encoding="utf-8")
    path.write_text(original, encoding="utf-8")

    config = save_settings({"weather.units": "fahrenheit", "autostart": True, "audio.silence_ms": 700}, path)

    assert config.weather.units == "fahrenheit" and config.autostart is True and config.audio.silence_ms == 700
    assert load_config(path) == config
    written = path.read_text(encoding="utf-8")
    original_comments = [line.strip() for line in original.splitlines() if line.strip().startswith("#")]
    written_comments = [line.strip() for line in written.splitlines() if line.strip().startswith("#")]
    assert written_comments == original_comments
    # Every other line is unchanged.
    changed = [(a, b) for a, b in zip(original.splitlines(), written.splitlines()) if a != b]
    assert len(original.splitlines()) == len(written.splitlines())
    assert all(any(k in a for k in ("units:", "autostart:", "silence_ms:")) for a, _ in changed)


def test_a_bad_value_leaves_the_file_untouched(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("privacy:\n  log_retention_days: 7  # a week\n", encoding="utf-8")

    with pytest.raises(pydantic.ValidationError):
        save_settings({"privacy.log_retention_days": 0}, path)

    assert path.read_text(encoding="utf-8") == "privacy:\n  log_retention_days: 7  # a week\n"


def test_adds_a_missing_section(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("autostart: false\n", encoding="utf-8")
    config = save_settings({"gui.start_minimized": True}, path)
    assert config.gui.start_minimized is True
    assert load_config(path).gui.start_minimized is True


def test_creates_the_file_if_needed(tmp_path):
    path = tmp_path / "new" / "config.yaml"
    assert save_settings({"search.enabled": False}, path).search.enabled is False
    assert load_config(path).search.enabled is False
