"""Windows toast notifications, alongside (not instead of) spoken
alerts -- so a timer/reminder firing while you're away from the PC, or
with audio muted, still leaves something to see.
"""
import logging

from win11toast import notify


def show_toast(title: str, body: str, log: logging.Logger | None = None) -> None:
    try:
        notify(title, body)
    except Exception:
        if log is not None:
            log.exception("Failed to show toast notification")
