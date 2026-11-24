"""Scoring speech recognition the way an assistant experiences it, for
scripts/stt_accuracy.py and scripts/benchmark.py.

Two numbers per transcript:
- Word error rate (WER): (substituted + deleted + inserted words) /
  words actually said -- the standard speech-recognition measure.
- Command accuracy: whether the transcript still runs the same command
  as what was actually said. This matters more for an assistant than
  WER: "open Spotify please" heard as "Open Spotify." has a WER of 33%
  but does exactly the right thing, while "pause" heard as "post" is
  one wrong word and a failed command.
"""
import re
from dataclasses import dataclass

from ash.nlu.grammar import parse

_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
    "fifteen": "15", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50", "hundred": "100",
}


def normalize(text: str) -> list[str]:
    """Words, compared fairly: lowercase, no punctuation (Whisper adds
    full stops and capitals that were never "said"), number words as
    digits, and "%" as "percent"."""
    text = text.lower().replace("%", " percent ")
    text = re.sub(r"[^\w\s']", " ", text)
    text = re.sub(r"(\d)([a-z])", r"\1 \2", text)  # "3pm" and "3 pm" are the same words
    return [_NUMBER_WORDS.get(word, word) for word in text.split()]


def word_errors(reference: str, hypothesis: str) -> tuple[int, int]:
    """(edit distance in words, number of reference words)."""
    ref, hyp = normalize(reference), normalize(hypothesis)
    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i] + [0] * len(hyp)
        for j, hyp_word in enumerate(hyp, start=1):
            current[j] = min(
                previous[j] + 1,                               # deleted
                current[j - 1] + 1,                            # inserted
                previous[j - 1] + (ref_word != hyp_word),      # substituted (or matched)
            )
        previous = current
    return previous[-1], len(ref)


def word_error_rate(references: list[str], hypotheses: list[str]) -> float:
    """Corpus WER: total errors / total reference words (not an average
    of per-clip rates, which would over-weight short commands)."""
    errors = words = 0
    for reference, hypothesis in zip(references, hypotheses, strict=True):
        e, n = word_errors(reference, hypothesis)
        errors += e
        words += n
    return errors / words if words else 0.0


# App names are matched fuzzily by Ash (ash/nlu/matcher.py), so "open
# Spatify" still opens Spotify; this similarity approximates that.
_APP_NAME_SIMILARITY = 80


def same_command(reference: str, hypothesis: str) -> bool:
    """Would the transcript run the same command, with the same target?
    Strict about the words of the target, except app names, which Ash
    matches fuzzily."""
    expected, heard = parse(reference), parse(hypothesis)
    if expected.intent != heard.intent:
        return False
    if expected.intent in ("open", "close_app"):
        from rapidfuzz import fuzz

        return fuzz.ratio(" ".join(normalize(expected.target)), " ".join(normalize(heard.target))) >= _APP_NAME_SIMILARITY
    return normalize(expected.target) == normalize(heard.target)


@dataclass(frozen=True)
class Summary:
    clips: int
    wer: float
    command_accuracy: float
    median_seconds: float
    p90_seconds: float


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def summarize(references: list[str], hypotheses: list[str], seconds: list[float]) -> Summary:
    correct = sum(same_command(r, h) for r, h in zip(references, hypotheses, strict=True))
    return Summary(
        clips=len(references),
        wer=word_error_rate(references, hypotheses),
        command_accuracy=correct / len(references) if references else 0.0,
        median_seconds=percentile(seconds, 0.5),
        p90_seconds=percentile(seconds, 0.9),
    )
