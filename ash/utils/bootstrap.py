"""Preflight checks run before the audio pipeline starts, so a missing
one-time model download fails with an actionable message instead of a
raw exception from deep inside openwakeword.
"""
import os
import sys

from openwakeword import get_pretrained_model_paths


def check_wake_word_models(keyword: str, model_paths: list[str] | None = None) -> None:
    if model_paths is None:
        model_paths = get_pretrained_model_paths(inference_framework="onnx")

    if any(os.path.basename(p).startswith(keyword) and os.path.exists(p) for p in model_paths):
        return

    print(
        f"Wake-word model {keyword!r} not found.\n"
        "Run this once to download it, then start Ash again:\n"
        f"    .venv\\Scripts\\python.exe scripts\\download_wake_word_models.py {keyword}\n",
        file=sys.stderr,
    )
    sys.exit(1)
