"""Running speech recognition on an NVIDIA graphics card.

Measured on an RTX 4060 with 50 real recordings: Whisper small took
141 ms per command on the GPU against 1,957 ms on the CPU (a 6-core
Ryzen), with the same accuracy (94% of commands right).

CTranslate2 (faster-whisper's engine) ships with CUDA and cuDNN but not
NVIDIA's cuBLAS library, which is a separate, optional install:
`pip install -r requirements-gpu.txt` (about 900 MB; only useful with an
NVIDIA card). CTranslate2 looks cuBLAS up by name on PATH, so its
folder is put on this process's PATH -- nothing system-wide changes.
"""
import logging
import os
from pathlib import Path

log = logging.getLogger("ash")

# Measured with the same accuracy as the CPU's int8 (float16: one more
# command wrong of 50), and it uses less graphics memory.
GPU_COMPUTE_TYPE = "int8_float16"
CPU_COMPUTE_TYPE = "int8"


def _cublas_folder() -> Path | None:
    try:
        import nvidia.cublas
    except ImportError:
        return None
    folder = Path(list(nvidia.cublas.__path__)[0]) / "bin"
    return folder if (folder / "cublas64_12.dll").exists() else None


def cuda_available() -> bool:
    """An NVIDIA GPU CTranslate2 can use, with cuBLAS installed (and now
    findable). False on any PC without them -- never an error."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() < 1:
            return False
    except Exception:
        return False
    folder = _cublas_folder()
    if folder is None:
        log.info("An NVIDIA GPU is present, but speech recognition runs on the CPU: "
                 "pip install -r requirements-gpu.txt to use it")
        return False
    if str(folder) not in os.environ.get("PATH", ""):
        os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
    return True
