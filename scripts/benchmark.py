r"""How long from the moment you stop talking to the moment Ash starts
answering, broken down by stage, on this PC:

1. End of speech: Ash waits for audio.silence_ms of silence to know
   you've finished (a setting, 900 ms by default; not measured).
2. Speech to text: Whisper transcribing the command.
3. Understanding and running it: grammar, then the command itself.
4. Start of the spoken reply: until the Windows voice starts speaking.

Commands are spoken by a Windows voice into memory (no microphone; the
same clips every run, so runs are comparable), and only commands that
work offline and change nothing are used. The voice is muted (volume 0)
while measuring stage 4, so nothing is heard.

Run: .venv\Scripts\python.exe scripts\benchmark.py [--model small] [--repeat 3]
"""
import argparse
import logging
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clips import read_wav, synthesize  # noqa: E402

from ash.actions.dispatcher import dispatch  # noqa: E402
from ash.config import load_config  # noqa: E402
from ash.evaluation import percentile, same_command  # noqa: E402
from ash.registry.loader import load_registry  # noqa: E402

# Offline, read-only: answering them changes nothing on the PC.
COMMANDS = [
    "what time is it",
    "what's the date today",
    "what's 15% of 80",
    "convert 5 miles to kilometers",
    "how many days until christmas",
    "what day is christmas",
    "how much storage do I have",
    "what's on my calendar",
    "what can you do",
    "thank you",
]


class FirstReply:
    """Stands in for Ash's voice: notes when the first reply is ready."""

    def __init__(self):
        self.first_at: float | None = None
        self.replies: list[str] = []

    def say(self, text: str) -> None:
        if self.first_at is None:
            self.first_at = time.perf_counter()
        self.replies.append(text)

    def is_speaking(self) -> bool:
        return False

    def stop_speaking(self) -> None:
        pass


def time_to_first_audio(texts: list[str]) -> list[float]:
    """Seconds from asking SAPI to speak until its first word plays
    (muted). SAPI's word event follows the audio position; its
    "utterance started" event fires as soon as synthesis begins, before
    any sound, so it would under-report."""
    import pyttsx3

    engine = pyttsx3.init()
    engine.setProperty("volume", 0.0)
    marks: list[float] = []
    engine.connect("started-word", lambda name, location, length: marks.append(time.perf_counter()))
    results = []
    for text in texts:
        marks.clear()
        start = time.perf_counter()
        engine.say(text)
        engine.runAndWait()
        if marks:
            results.append(marks[0] - start)
    engine.stop()
    return results


def _ms(seconds: float) -> str:
    ms = seconds * 1000
    return f"{ms:.1f} ms" if ms < 10 else f"{ms:.0f} ms"


def piper_time_to_first_audio(texts: list[str], voice_name: str) -> list[float]:
    """Seconds until Piper has the first sentence's audio ready (it plays
    as soon as it's ready; nothing is played here)."""
    from piper import PiperVoice

    from ash.setup_models import piper_voice_path

    voice = PiperVoice.load(piper_voice_path(voice_name))
    for _ in voice.synthesize("Ready."):  # warm-up, as Ash does at startup
        pass
    results = []
    for text in texts:
        start = time.perf_counter()
        next(iter(voice.synthesize(text)))
        results.append(time.perf_counter() - start)
    return results


def stats(values: list[float]) -> str:
    if not values:
        return "n/a"
    return f"{_ms(statistics.median(values))} (90th percentile {_ms(percentile(values, 0.9))})"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="small", help="Whisper model size (Ash uses small)")
    parser.add_argument("--repeat", type=int, default=3, help="times to run each command")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto",
                        help="where speech recognition runs (auto: the NVIDIA GPU if it works)")
    parser.add_argument("--voice", choices=["windows", "piper"], default="windows",
                        help="which voice to time (piper needs piper-tts and the voice downloaded)")
    args = parser.parse_args()

    logging.disable(logging.CRITICAL)
    config = load_config()
    registry = load_registry()
    log = logging.getLogger("benchmark")

    print("Making the command clips with a Windows voice...")
    with tempfile.TemporaryDirectory() as folder:
        clips = []
        for i, text in enumerate(COMMANDS):
            path = Path(folder) / f"{i}.wav"
            synthesize(text, path)
            clips.append((text, read_wav(path)))

    from ash.audio.stt import SpeechToText

    print(f"Loading Whisper {args.model}...")
    load_start = time.perf_counter()
    stt = SpeechToText(model_size=args.model, device=args.device)
    load_seconds = time.perf_counter() - load_start
    stt.transcribe(clips[0][1])  # warm-up, not timed

    stt_times, dispatch_times, replies, understood = [], [], [], 0
    for _ in range(args.repeat):
        for text, audio in clips:
            start = time.perf_counter()
            heard = stt.transcribe(audio)
            stt_times.append(time.perf_counter() - start)
            understood += same_command(text, heard)

            voice = FirstReply()
            start = time.perf_counter()
            dispatch(heard, registry, voice, log, config)
            if voice.first_at is not None:
                dispatch_times.append(voice.first_at - start)
                replies.append(voice.replies[0])
    if args.voice == "piper":
        tts_times = piper_time_to_first_audio(replies[: len(COMMANDS)], config.voice.piper_voice)
    else:
        tts_times = time_to_first_audio(replies[: len(COMMANDS)])

    silence = config.audio.silence_ms / 1000
    total = silence + statistics.median(stt_times) + statistics.median(dispatch_times) + statistics.median(tts_times)
    runs = args.repeat * len(COMMANDS)
    where = "GPU" if stt.device == "cuda" else "CPU"
    print(f"\nEnd of speech to first spoken word, {runs} runs of {len(COMMANDS)} commands, "
          f"Whisper {args.model} on the {where}:\n")
    print("| Stage | Median (90th percentile) |")
    print("|---|---|")
    print(f"| End of speech (audio.silence_ms setting) | {silence * 1000:.0f} ms |")
    print(f"| Speech to text | {stats(stt_times)} |")
    print(f"| Understanding and running the command | {stats(dispatch_times)} |")
    voice = "Piper " + config.voice.piper_voice if args.voice == "piper" else "Windows voice"
    print(f"| Start of the spoken reply ({voice}) | {stats(tts_times)} |")
    print(f"| **Total (medians)** | **{total * 1000:.0f} ms** |")
    print(f"\nWhisper {args.model} took {load_seconds:.1f} s to load (once, at startup). "
          f"{understood}/{runs} transcripts ran the intended command.")


if __name__ == "__main__":
    main()
