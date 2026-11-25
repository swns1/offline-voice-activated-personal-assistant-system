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
from pathlib import Path

from ash.privacy import egress
from ash.utils.paths import MODELS_DIR, resolve_wake_word_keyword

WHISPER_MODEL = "small"
# Rough sizes, for the question you're asked.
WAKE_WORD_MB = 10
WHISPER_MB = {"tiny": 75, "base": 145, "small": 465, "medium": 1500}

# Suggested Piper voices: all trained on openly licensed recordings
# (several other Piper voices are non-commercial only).
PIPER_VOICES = {
    "en_US-ljspeech-medium": ("American English, female", 64, "public domain"),
    "en_US-ljspeech-high": ("American English, female, higher quality", 115, "public domain"),
    "en_GB-alba-medium": ("Scottish English, female", 64, "CC BY 4.0"),
}
_PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def wake_word_model_missing(keyword: str) -> bool:
    from openwakeword import get_pretrained_model_paths

    from ash.audio.personal_wake_word import is_personal

    if keyword.endswith(".onnx") or is_personal(keyword):  # one you trained: nothing to download
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


def piper_voice_path(name: str) -> Path:
    return MODELS_DIR / "piper" / f"{name}.onnx"


def piper_installed() -> bool:
    import importlib.util

    return importlib.util.find_spec("piper") is not None


def piper_voice_missing(name: str) -> bool:
    path = piper_voice_path(name)
    return not (path.exists() and path.with_suffix(".onnx.json").exists())


def piper_voice_urls(name: str) -> list[str]:
    """"en_US-ljspeech-medium" -> the model and its settings file, in
    the rhasspy/piper-voices layout (en/en_US/ljspeech/medium/...)."""
    locale, speaker, quality = name.split("-", 2)
    folder = f"{_PIPER_BASE}/{locale.split('_')[0]}/{locale}/{speaker}/{quality}/{name}"
    return [f"{folder}.onnx", f"{folder}.onnx.json"]


def download_piper_voice(name: str) -> None:
    """Raises egress.OfflineModeError in offline mode. Written to a
    temporary name first, so an interrupted download is never used."""
    target = piper_voice_path(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    for url, path in zip(piper_voice_urls(name), (target, target.with_suffix(".onnx.json")), strict=True):
        response = egress.get(url, feature=egress.MODEL_DOWNLOAD.key, stream=True, timeout=60)
        response.raise_for_status()
        partial = path.with_name(path.name + ".part")
        with open(partial, "wb") as f:
            for block in response.iter_content(1024 * 1024):
                f.write(block)
        os.replace(partial, path)


def missing_downloads(keyword: str, whisper_size: str = WHISPER_MODEL, piper_voice: str | None = None) -> list[str]:
    """What still has to be downloaded, described for a person.
    `piper_voice`: the Piper voice in use, if voice.engine is "piper"."""
    missing = []
    if piper_voice and piper_installed() and piper_voice_missing(piper_voice):
        size = PIPER_VOICES.get(piper_voice, ("", None, ""))[1]
        missing.append(f"the {piper_voice} voice ({f'about {size} MB, ' if size else ''}from Hugging Face)")
    if wake_word_model_missing(keyword):
        missing.append(f"the wake-word model (about {WAKE_WORD_MB} MB, from the openWakeWord project on GitHub)")
    if whisper_model_missing(whisper_size):
        size = WHISPER_MB.get(whisper_size)
        missing.append(f"the speech-recognition model ({f'about {size} MB, ' if size else ''}from Hugging Face)")
    return missing


def download_question(missing: list[str]) -> str:
    listed = missing[0] if len(missing) == 1 else ", ".join(missing[:-1]) + " and " + missing[-1]
    return (f"Before Ash can listen, it needs to download {listed}, once. "
            "Nothing about you is sent, and it's recorded in the network log. "
            "Download now?")


def download_wake_word_model(keyword: str) -> None:
    """Raises egress.OfflineModeError in offline mode."""
    from openwakeword.utils import download_models

    egress.check(egress.MODEL_DOWNLOAD.key)
    egress.record_use(egress.MODEL_DOWNLOAD.key, domain="github.com")
    download_models([keyword])
