"""Parsed-command shape. `intent` is a plain str tag rather than a class
hierarchy — new tags (media, system, assistant_control) are added in
later phases without new classes, since every handler just switches on
this string.
"""
from dataclasses import dataclass


@dataclass
class ParsedCommand:
    intent: str  # "open" | "search" | "unknown"
    target: str
    # False only for the grammar's last-resort "no verb recognized, treat
    # the whole utterance as open <target>" default -- lets a caller (see
    # ash/actions/semantic_fallback.py) tell "you explicitly said open X"
    # apart from "nothing else matched so we guessed open", since only
    # the latter is worth a second look.
    explicit: bool = True
