"""Rotating file logging, set up first so nothing (including early Phase 0
smoke tests) can fail silently once Ash runs headless via pythonw.exe."""
import logging
from logging.handlers import RotatingFileHandler

from ash.utils.paths import LOG_DIR, ensure_app_data_dirs

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    ensure_app_data_dirs()

    logger = logging.getLogger("ash")
    logger.setLevel(level)

    if logger.handlers:
        return logger  # idempotent — safe to call from multiple entry points

    file_handler = RotatingFileHandler(
        LOG_DIR / "ash.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(console_handler)

    return logger
