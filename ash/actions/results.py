"""Handler return type. A plain `None` return (today's every handler)
still means "done" -- see ash/actions/dispatcher.py's normalization --
so this is purely additive for handlers that need to ask a clarifying
follow-up question before finishing.

Kept in its own module rather than in dispatcher.py to avoid a circular
import: action modules (open_app.py, search.py, spotify.py) need this
type but dispatcher.py imports *them*.
"""
from collections.abc import Callable
from dataclasses import dataclass

# The answers a yes/no question offers as buttons in the desktop window.
# Spoken answers are still matched loosely (confirmation.is_affirmative).
YES_NO = ("Yes", "No")


@dataclass
class HandlerResult:
    done: bool = True
    question: str | None = None
    resume: Callable[[str], "HandlerResult"] | None = None
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
    # Answers the desktop window shows as buttons (e.g. YES_NO). Empty
    # for open questions ("Which app?"): those are answered by typing or
    # speaking. Clicking a button is the same as saying its text.
    choices: tuple[str, ...] = ()
