"""The command words given to Whisper as hints (ash/audio/vocabulary.py)."""
from ash.audio.vocabulary import _STOP_WORDS, LIMIT, command_vocabulary, hotwords


def test_the_words_the_accuracy_study_found_misheard_are_included():
    words = set(command_vocabulary())
    for misheard in ("pause", "city", "timer", "resume", "Spotify"):
        assert misheard in words, misheard


def test_no_filler_and_within_whispers_prompt_budget():
    words = command_vocabulary()
    assert len(words) == LIMIT == len(set(words))
    assert not set(words) & _STOP_WORDS
    assert len(hotwords()) < 600  # characters; Whisper's prompt holds ~220 tokens
