"""Handler return type. A plain `None` return (today's every handler)
still means "done" -- see ash/actions/dispatcher.py's normalization --
so this is purely additive for handlers that need to ask a clarifying
follow-up question before finishing.

Kept in its own module rather than in dispatcher.py to avoid a circular
import: action modules (open_app.py, search.py, spotify.py) need this
type but dispatcher.py imports *them*.
"""
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class HandlerResult:
    done: bool = True
    question: str | None = None
    resume: Optional[Callable[[str], "HandlerResult"]] = None
