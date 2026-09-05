"""Phase 2 smoke test: press Enter, speak after the countdown, see the
transcript. Loads the whisper model once, then loops so you can try a
few phrases (including a game title) without paying reload cost each time.

Run: .venv\\Scripts\\python.exe scripts\\phase2_stt_test.py
"""
import time

from ash.audio.recorder import record_fixed
from ash.audio.stt import SpeechToText

RECORD_SECONDS = 4.0


def countdown(n: int = 3) -> None:
    for i in range(n, 0, -1):
        print(f"  recording in {i}...")
        time.sleep(1)
    print("  >>> SPEAK NOW <<<")


def main() -> None:
    print("Loading faster-whisper model (small, cpu, int8)...")
    stt = SpeechToText()
    print("Model loaded.\n")

    try:
        while True:
            input("Press Enter to record a phrase (Ctrl+C to quit)...")
            countdown()
            audio = record_fixed(RECORD_SECONDS)
            print("  transcribing...")
            text = stt.transcribe(audio)
            print(f"  >>> TRANSCRIPT: {text!r}\n")
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.")


if __name__ == "__main__":
    main()
