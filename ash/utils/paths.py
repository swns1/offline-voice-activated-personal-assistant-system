"""Filesystem locations Ash reads/writes at runtime."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
MODELS_DIR = PROJECT_ROOT / "models"

APP_DATA_DIR = Path(os.environ["LOCALAPPDATA"]) / "Ash"
LOG_DIR = APP_DATA_DIR / "logs"
SECRETS_DIR = APP_DATA_DIR

CONFIG_PATH = CONFIG_DIR / "config.yaml"
REGISTRY_MANUAL_PATH = CONFIG_DIR / "registry.yaml"
REGISTRY_AUTO_PATH = CONFIG_DIR / "registry.auto.yaml"
TIMERS_STATE_PATH = APP_DATA_DIR / "timers.json"
MEMORY_PATH = APP_DATA_DIR / "memory.json"
VOICEPRINT_PATH = APP_DATA_DIR / "voiceprint.json"
PRIVACY_STATE_PATH = APP_DATA_DIR / "privacy_state.json"
NETWORK_LOG_PATH = APP_DATA_DIR / "network_log.json"


def ensure_app_data_dirs() -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def resolve_wake_word_keyword(keyword: str) -> str:
    """A bundled openWakeWord model name (e.g. "hey_jarvis") is passed
    straight through -- openWakeWord resolves those itself. A
    custom-trained model (e.g. from openWakeWord's own training
    pipeline/notebook -- see README) is referenced by a .onnx file path;
    if that path is relative, resolve it against MODELS_DIR so it works
    regardless of the process's current working directory (relevant for
    autostart, which launches via a Registry Run key with an
    unpredictable CWD). An already-absolute .onnx path is left alone."""
    if keyword.endswith(".onnx") and not os.path.isabs(keyword):
        return str(MODELS_DIR / keyword)
    return keyword
