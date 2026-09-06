"""System tray icon -- lets Ash run without a visible console window
(e.g. via pythonw.exe + autostart) while still showing it's running and
giving a way to quit it. pystray's Windows backend owns the calling
thread's message loop (icon.run() blocks it), so the actual assistant
loop runs on a background thread instead; the tray icon owns the main
thread. Confirmed live that icon.run()/icon.stop() work correctly on
this machine before wiring this into main.py.

Quit exits the whole process immediately (os._exit) rather than trying
to signal the background thread to unwind gracefully -- it's typically
blocked deep inside a blocking mic read waiting for the wake word, with
no cheap way to interrupt that from another thread. The only cleanup
main.py's normal shutdown path did (wake_detector.delete(), a no-op;
tts.stop(), whose thread is a daemon anyway) isn't load-bearing enough
to justify the extra complexity of a clean cross-thread shutdown signal.
"""
import logging
import os
import threading
from typing import Callable

import pystray
from PIL import Image, ImageDraw

from ash.utils.paths import LOG_DIR

_ICON_SIZE = 64


def _make_icon_image() -> Image.Image:
    image = Image.new("RGBA", (_ICON_SIZE, _ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, _ICON_SIZE - 8, _ICON_SIZE - 8), fill=(0, 122, 255, 255))
    return image


def _open_logs_folder(icon, item) -> None:
    os.startfile(LOG_DIR)


def _run_worker(work: Callable[[], None], icon: pystray.Icon, log: logging.Logger) -> None:
    """Runs the real assistant loop. If it exits for any reason (crash
    or otherwise), tears down the tray icon and the process too, rather
    than leaving a tray icon sitting there for an assistant that's no
    longer running."""
    try:
        work()
    except Exception:
        log.exception("Assistant loop crashed")
    finally:
        icon.stop()
        os._exit(1)


def _on_quit(icon: pystray.Icon, item, log: logging.Logger) -> None:
    log.info("Tray: Quit clicked, exiting")
    icon.stop()
    os._exit(0)


def run_with_tray(work: Callable[[], None], log: logging.Logger) -> None:
    """Blocks the calling thread running the tray icon's message loop
    while work() runs on a background thread."""
    menu = pystray.Menu(
        pystray.MenuItem("Open logs folder", _open_logs_folder),
        pystray.MenuItem("Quit Ash", lambda icon, item: _on_quit(icon, item, log)),
    )
    icon = pystray.Icon("ash", _make_icon_image(), "Ash", menu)

    threading.Thread(target=_run_worker, args=(work, icon, log), daemon=True).start()
    icon.run()
