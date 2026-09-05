"""One-time fetch of openWakeWord's pretrained model files (melspectrogram,
embedding, VAD, and the requested wake-word models) from the openWakeWord
GitHub releases. No account/API key involved -- just a plain download.

Run: .venv\\Scripts\\python.exe scripts\\download_wake_word_models.py [model ...]
Defaults to "hey_jarvis" if no model names are given.
"""
import sys

from openwakeword.utils import download_models

if __name__ == "__main__":
    models = sys.argv[1:] or ["hey_jarvis"]
    print(f"Downloading openWakeWord models: {models}")
    download_models(models)
    print("Done.")
