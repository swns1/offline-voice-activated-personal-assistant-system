"""File logging, set up first so nothing (including early startup
failures) can fail silently once Ash runs headless via pythonw.exe.

Logs roll over to a new file each day and only the last
`privacy.log_retention_days` days are kept (RA 10173 Sec. 11: keep
personal data no longer than needed). apply_log_retention() also sweeps
any older log file left behind, e.g. by earlier versions of Ash that
rotated by size instead of by day. What may appear *in* a log line is
decided separately, by ash/privacy/redact.py.
"""
import logging
import time
from logging.handlers import TimedRotatingFileHandler

from ash.utils.paths import LOG_DIR, ensure_app_data_dirs

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
LOG_FILE_NAME = "ash.log"
DEFAULT_RETENTION_DAYS = 7

_SECONDS_PER_DAY = 24 * 60 * 60


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    ensure_app_data_dirs()

    logger = logging.getLogger("ash")
    logger.setLevel(level)

    if logger.handlers:
        return logger  # idempotent — safe to call from multiple entry points

    # Rolls over at midnight; on startup it also rolls over straight away
    # if the existing file is from an earlier day (the handler computes
    # the next rollover from the file's modification time).
    # delay=True: the file isn't opened until the first log line, so
    # apply_log_retention() can still delete a stale one at startup.
    file_handler = TimedRotatingFileHandler(
        LOG_DIR / LOG_FILE_NAME, when="midnight", backupCount=DEFAULT_RETENTION_DAYS,
        encoding="utf-8", delay=True,
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(console_handler)

    return logger


def apply_log_retention(retention_days: int, logger: logging.Logger | None = None,
                        now: float | None = None) -> list[str]:
    """Keep at most `retention_days` days of logs: sets how many daily
    files the handler keeps, and deletes any log file in LOG_DIR last
    written more than `retention_days` days ago. Returns the names of
    files deleted."""
    logger = logger or logging.getLogger("ash")
    for handler in logger.handlers:
        if isinstance(handler, TimedRotatingFileHandler):
            handler.backupCount = retention_days

    cutoff = (now if now is not None else time.time()) - retention_days * _SECONDS_PER_DAY
    deleted = []
    for path in LOG_DIR.glob(LOG_FILE_NAME + "*"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                deleted.append(path.name)
        except OSError:
            pass  # open (already being written to) or already gone -- next startup
    return deleted


def close_log_files(logger: logging.Logger | None = None) -> None:
    """Close Ash's open log file so it can be deleted ("delete all my
    data" -- Windows won't delete a file that's open). The handler reopens
    a fresh file by itself on the next log line."""
    logger = logger or logging.getLogger("ash")
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.close()
