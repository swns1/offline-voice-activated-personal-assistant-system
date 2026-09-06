import logging

from ash.tray import icon as icon_module

log = logging.getLogger("test")


class FakeIcon:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def _no_real_exit(monkeypatch):
    calls = []
    monkeypatch.setattr(icon_module.os, "_exit", lambda code: calls.append(code))
    return calls


def test_run_worker_success_stops_icon_and_exits(monkeypatch):
    exit_calls = _no_real_exit(monkeypatch)
    fake_icon = FakeIcon()

    icon_module._run_worker(lambda: None, fake_icon, log)

    assert fake_icon.stopped is True
    assert exit_calls == [1]  # even a clean return exits -- no assistant loop means no tray icon


def test_run_worker_crash_is_logged_and_still_exits(monkeypatch):
    exit_calls = _no_real_exit(monkeypatch)
    fake_icon = FakeIcon()

    def boom():
        raise RuntimeError("assistant loop blew up")

    icon_module._run_worker(boom, fake_icon, log)  # must not raise

    assert fake_icon.stopped is True
    assert exit_calls == [1]


def test_on_quit_stops_icon_and_exits_zero(monkeypatch):
    exit_calls = _no_real_exit(monkeypatch)
    fake_icon = FakeIcon()

    icon_module._on_quit(fake_icon, None, log)

    assert fake_icon.stopped is True
    assert exit_calls == [0]


def test_open_logs_folder_calls_startfile(monkeypatch):
    calls = []
    monkeypatch.setattr(icon_module.os, "startfile", lambda path: calls.append(path))

    icon_module._open_logs_folder(None, None)

    assert calls == [icon_module.LOG_DIR]


def test_make_icon_image_returns_an_image():
    image = icon_module._make_icon_image()
    assert image.size == (icon_module._ICON_SIZE, icon_module._ICON_SIZE)
