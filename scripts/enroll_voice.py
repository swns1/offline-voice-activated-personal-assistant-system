"""One-time voice enrollment for the optional voice-match gate on
destructive-action confirmations (config.security.voice_gate_enabled) --
see ash/security/voice_gate.py for what this actually does and its
accuracy caveats. Records you speaking for a few seconds and saves an
MFCC-based voiceprint to match future confirmations against.

Run: .venv\\Scripts\\python.exe scripts\\enroll_voice.py
"""
import time

from ash.audio.recorder import record_fixed
from ash.security.voice_gate import enroll

_SECONDS = 5.0

if __name__ == "__main__":
    print(f"Speak naturally for about {_SECONDS:.0f} seconds after the countdown -- "
          "a sentence or two works better than a single word, e.g. read this "
          "sentence aloud in your normal voice.")
    for i in (3, 2, 1):
        print(i)
        time.sleep(1)
    print("Recording...")
    audio = record_fixed(_SECONDS)
    print("Done.")

    if enroll(audio):
        print("Voice enrolled. Set security.voice_gate_enabled: true in "
              "config/config.yaml to start using it.")
    else:
        print("That recording was too short/quiet to enroll from -- try again.")
