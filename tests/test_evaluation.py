"""Speech-recognition scoring (ash/evaluation.py)."""
import pytest

from ash.evaluation import normalize, percentile, same_command, summarize, word_error_rate, word_errors


def test_punctuation_capitals_and_number_words_dont_count_as_errors():
    assert normalize("Set a timer for ten minutes.") == ["set", "a", "timer", "for", "10", "minutes"]
    assert word_errors("what's 15% of 80", "What's 15 percent of 80?") == (0, 5)


@pytest.mark.parametrize("reference, hypothesis, errors", [
    ("open spotify", "open spotify", 0),
    ("open spotify", "open spot a fly", 3),      # one substitution, two insertions
    ("pause the music", "pause music", 1),        # deletion
    ("next track", "", 2),                        # nothing heard
])
def test_word_errors(reference, hypothesis, errors):
    assert word_errors(reference, hypothesis)[0] == errors


def test_corpus_wer_weights_by_words_not_by_clip():
    # 1 error in 1 word + 0 errors in 9 words = 1/10, not the average 50%.
    assert word_error_rate(["stop", "set a timer for 10 minutes to check oven"],
                           ["shop", "set a timer for 10 minutes to check oven"]) == pytest.approx(0.1)


def test_a_transcript_can_be_wrong_and_still_run_the_right_command():
    assert same_command("open spotify please", "Open Spotify.")       # WER 1/3, same command
    assert same_command("set a timer for ten minutes", "Set a timer for 10 minutes.")
    assert not same_command("set a timer for ten minutes", "set the timer for 10 minutes")
    assert same_command("what's the weather tomorrow", "What's the weather tomorrow?")
    assert not same_command("open spotify", "open spot a fly")
    assert not same_command("pause", "post")


def test_summary():
    summary = summarize(["open spotify", "pause"], ["Open Spotify.", "post"], [0.5, 1.5])
    assert summary.clips == 2 and summary.command_accuracy == 0.5
    assert summary.wer == pytest.approx(1 / 3)
    assert percentile([3, 1, 2], 0.5) == 2 and percentile([], 0.9) == 0.0
