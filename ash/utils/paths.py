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


def ensure_app_data_dirs() -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
