"""The words Ash's commands are made of, given to Whisper as hotwords
so it listens for them.

Short command words are where speech recognition goes wrong most:
measured on 50 recordings of a real user saying Ash's commands, Whisper
small heard "pause" as "boss", "list" as "lease" and "city" as "CT".
Given these words as hints, its word error rate fell from 12.6% to 5.7%
and the share of commands it got right rose from 86% to 94%, for about
0.1 s more per command (scripts/stt_accuracy.py reproduces this on your
own voice). A check with free-form sentences (searches, notes) showed no
harm to transcription outside the command words.

Generated from the skill catalog, so new commands' words are included
automatically.
"""
import re
from collections import Counter
from functools import cache

from ash.skills import registry as skills

# Filler that every command shares; hinting it tells Whisper nothing.
_STOP_WORDS = {
    "the", "a", "an", "my", "to", "for", "of", "in", "on", "is", "it", "i", "me", "and", "what", "what's", "whats",
    "do", "you", "your", "this", "that", "at", "by", "with", "are", "be", "how", "can", "some", "any", "all", "up",
    "down", "off", "about", "from", "please", "there", "have", "has", "was", "will", "into", "out", "much", "many",
}
# Whisper's prompt holds about 220 tokens; this stays well inside it.
LIMIT = 60
_PROPER_NOUNS = {"spotify": "Spotify"}


@cache
def command_vocabulary(limit: int = LIMIT) -> tuple[str, ...]:
    """The commands' distinctive words, most used first."""
    counts: Counter[str] = Counter()
    for skill in skills.visible_skills():
        for phrase in skill.phrases + skill.verbs:
            for word in re.findall(r"[a-z']+", phrase.lower()):
                if word not in _STOP_WORDS and len(word) > 2:
                    counts[word] += 1
    return tuple(_PROPER_NOUNS.get(word, word) for word, _ in counts.most_common(limit))


def hotwords() -> str:
    return " ".join(command_vocabulary())
