"""Phase 0 smoke test: list mic input devices and speak a test sentence.

Run: .venv\\Scripts\\python.exe scripts\\phase0_smoketest.py
"""
import sounddevice as sd
import pyttsx3


def list_input_devices() -> None:
    print("=== Input devices ===")
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            default_marker = " (default)" if idx == sd.default.device[0] else ""
            print(f"[{idx}] {dev['name']}{default_marker} "
                  f"(in ch: {dev['max_input_channels']}, "
                  f"default sr: {dev['default_samplerate']})")


def speak_test_sentence() -> None:
    print("\n=== TTS ===")
    engine = pyttsx3.init()
    engine.say("Hello, this is Ash. Text to speech is working.")
    engine.runAndWait()
    print("TTS finished speaking.")


if __name__ == "__main__":
    list_input_devices()
    speak_test_sentence()
