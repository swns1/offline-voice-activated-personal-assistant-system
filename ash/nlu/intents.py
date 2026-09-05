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
