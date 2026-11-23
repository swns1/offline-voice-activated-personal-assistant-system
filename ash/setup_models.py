"""First-run model downloads, asked about first.

Ash needs two pretrained models on this PC before it can listen:
openWakeWord's wake-word model (a few MB, from the openWakeWord project's
GitHub releases) and Whisper's speech-recognition model (a few hundred
MB, from Hugging Face). Neither is shipped inside Ash's download: the
wake-word models have their own licence, and the speech model is large.

The desktop window asks before downloading (see ash/gui/app.py). Both
downloads are checked against offline mode and written to the network
log as the "model downloads" online feature; nothing about you is sent.
openWakeWord's downloader makes its own web requests, so like Spotify
it's checked and logged per download rather than passing through
ash/privacy/egress.py's get().
"""
import os

from ash.privacy import egress
from ash.utils.paths import resolve_wake_word_keyword

WHISPER_MODEL = "small"
# Rough sizes, for the question you're asked.
WAKE_WORD_MB = 10
WHISPER_MB = {"tiny": 75, "base": 145, "small": 465, "medium": 1500}


def wake_word_model_missing(keyword: str) -> bool:
    from openwakeword import get_pretrained_model_paths

    if keyword.endswith(".onnx"):  # a custom model you trained: nothing to download
        return False
    paths = get_pretrained_model_paths(inference_framework="onnx")
    return not any(os.path.basename(p).startswith(keyword) and os.path.exists(p) for p in paths)


def custom_wake_word_missing(keyword: str) -> bool:
    return keyword.endswith(".onnx") and not os.path.exists(resolve_wake_word_keyword(keyword))


def whisper_model_missing(size: str = WHISPER_MODEL) -> bool:
    from faster_whisper.utils import download_model

    try:
        download_model(size, local_files_only=True)
    except Exception:  # huggingface_hub's LocalEntryNotFoundError, or no cache at all
        return True
    return False


def missing_downloads(keyword: str, whisper_size: str = WHISPER_MODEL) -> list[str]:
    """What still has to be downloaded, described for a person."""
    missing = []
    if wake_word_model_missing(keyword):
        missing.append(f"the wake-word model (about {WAKE_WORD_MB} MB, from the openWakeWord project on GitHub)")
    if whisper_model_missing(whisper_size):
        size = WHISPER_MB.get(whisper_size)
        missing.append(f"the speech-recognition model ({f'about {size} MB, ' if size else ''}from Hugging Face)")
    return missing


def download_question(missing: list[str]) -> str:
    listed = missing[0] if len(missing) == 1 else " and ".join(missing)
    return (f"Before Ash can listen, it needs to download {listed}, once. "
            "Nothing about you is sent, and it's recorded in the network log. "
            "Download now?")


def download_wake_word_model(keyword: str) -> None:
    """Raises egress.OfflineModeError in offline mode."""
    from openwakeword.utils import download_models

    egress.check(egress.MODEL_DOWNLOAD.key)
    egress.record_use(egress.MODEL_DOWNLOAD.key, domain="github.com")
    download_models([keyword])
