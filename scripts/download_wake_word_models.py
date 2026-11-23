r"""One-time fetch of openWakeWord's pretrained model files (melspectrogram,
embedding, VAD, and the requested wake-word models) from the openWakeWord
GitHub releases. No account/API key involved -- just a plain download,
blocked in offline mode and recorded in Ash's network log (see
ash/setup_models.py; the desktop window offers the same download on
first start).

Run: .venv\Scripts\python.exe scripts\download_wake_word_models.py [model ...]
Defaults to "hey_jarvis" if no model names are given.
"""
import sys

from ash.setup_models import download_wake_word_model

if __name__ == "__main__":
    models = sys.argv[1:] or ["hey_jarvis"]
    print(f"Downloading openWakeWord models: {models}")
    for model in models:
        download_wake_word_model(model)
    print("Done.")
