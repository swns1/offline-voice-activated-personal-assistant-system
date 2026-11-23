"""The --selftest report (ash/selftest.py). The real engine checks run
against the installed models, so they're exercised by running
`python -m ash --selftest`, not here."""
from ash.selftest import _timed, report


def test_optional_extras_dont_fail_the_selftest():
    text, passed = report([("Wake word", True, "ok"), ("Ollama", False, "not running")])
    assert passed
    assert "[  --] Ollama: not running" in text


def test_a_required_check_fails_it():
    text, passed = report([("Speech recognition", False, "model not downloaded yet")])
    assert not passed
    assert text.endswith("Some required checks failed.")


def test_a_check_that_raises_is_reported_not_raised():
    def boom():
        raise RuntimeError("DLL load failed")
    name, ok, detail = _timed("Wake word", boom)
    assert not ok and detail == "RuntimeError: DLL load failed"
