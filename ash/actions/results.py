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
    # Set only by ash/actions/confirmation.py's wrap_with_confirmation()
    # when config.security.voice_gate_enabled -- tells ash/main.py's loop
    # to check the follow-up answer's raw audio against the enrolled
    # voiceprint (see ash/security/voice_gate.py) before calling resume()
    # at all, rather than resume() itself needing access to raw audio.
    requires_voice_match: bool = False
    # What ash/main.py's loop says if no answer comes in time. "Never
    # mind." suits a dropped command; a setup question says something
    # that tells you it'll come back ("I'll ask again next time.").
    timeout_reply: str = "Never mind."
