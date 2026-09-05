from types import SimpleNamespace

from ash.registry.start_menu_scan import scan_start_menu


class _FakeShell:
    """Maps a .lnk path (str) to (Targetpath, Arguments), as WScript.Shell's
    CreateShortcut(...) would resolve it."""

    def __init__(self, mapping: dict[str, tuple[str, str]]):
        self._mapping = mapping

    def CreateShortcut(self, path: str):
        target, args = self._mapping.get(path, ("", ""))
        return SimpleNamespace(Targetpath=target, Arguments=args)


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def test_resolves_lnk_to_app_entry(tmp_path):
    start_menu = tmp_path / "Start Menu"
    lnk = _touch(start_menu / "Notepad.lnk")
    exe = _touch(tmp_path / "notepad.exe")
    shell = _FakeShell({str(lnk): (str(exe), "")})

    entries = scan_start_menu(search_dirs=[start_menu], shell_factory=lambda: shell)

    assert len(entries) == 1
    assert entries[0]["id"] == "notepad"
    assert entries[0]["names"] == ["notepad"]
    assert entries[0]["launch"] == {"type": "exe", "target": str(exe)}
    assert entries[0]["source"] == "start_menu"


def test_skips_junk_shortcuts(tmp_path):
    start_menu = tmp_path / "Start Menu"
    uninstall_lnk = _touch(start_menu / "Uninstall Notepad.lnk")
    missing_target_lnk = _touch(start_menu / "Broken.lnk")
    folder_lnk = _touch(start_menu / "File Explorer.lnk")
    exe = _touch(tmp_path / "uninstall.exe")

    shell = _FakeShell({
        str(uninstall_lnk): (str(exe), ""),
        str(missing_target_lnk): (str(tmp_path / "does_not_exist.exe"), ""),
        str(folder_lnk): ("", ""),
    })

    entries = scan_start_menu(search_dirs=[start_menu], shell_factory=lambda: shell)

    assert entries == []


def test_dedupes_same_target_across_search_dirs(tmp_path):
    per_user = tmp_path / "per_user"
    all_users = tmp_path / "all_users"
    per_user_lnk = _touch(per_user / "Discord.lnk")
    all_users_lnk = _touch(all_users / "Discord Inc.lnk")
    exe = _touch(tmp_path / "discord.exe")

    shell = _FakeShell({
        str(per_user_lnk): (str(exe), ""),
        str(all_users_lnk): (str(exe), ""),
    })

    entries = scan_start_menu(search_dirs=[per_user, all_users], shell_factory=lambda: shell)

    assert len(entries) == 1
    assert set(entries[0]["names"]) == {"discord", "discord inc"}


def test_missing_search_dir_is_skipped(tmp_path):
    entries = scan_start_menu(
        search_dirs=[tmp_path / "does_not_exist"], shell_factory=lambda: _FakeShell({}),
    )
    assert entries == []
