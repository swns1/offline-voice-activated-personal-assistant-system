# PyInstaller build for Ash: a folder (dist/Ash/) with Ash.exe, zipped
# for a GitHub release by scripts/build_release.py. Run that script
# rather than PyInstaller directly: it also makes the icon.
#
# Not included, on purpose: the wake-word and speech-recognition models.
# Ash asks before downloading them on first start (ash/setup_models.py).
# The openWakeWord models have their own licence, and the speech model
# is a few hundred MB.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
BUILD = ROOT / "build"

datas = [
    (str(ROOT / "config" / "config.yaml"), "config"),
    (str(ROOT / "config" / "registry.yaml"), "config"),
    (str(ROOT / "docs" / "PRIVACY.md"), "docs"),
    (str(ROOT / "README.md"), "."),
    (str(ROOT / "LICENSE"), "."),
]
datas += collect_data_files("faster_whisper")   # its voice-activity model
datas += collect_data_files("pint")             # unit definitions
datas += collect_data_files("openwakeword", excludes=["resources/models/*"])

hiddenimports = [
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",
    *collect_submodules("winrt.windows.media.control"),
    *collect_submodules("winrt.windows.foundation"),
]

a = Analysis(
    [str(ROOT / "packaging" / "ash_entry.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    # piper: the optional natural voice is GPL-licensed, and Ash's
    # release is MIT, so it's never bundled (users install it themselves).
    # nvidia: the optional GPU library for speech recognition (900 MB);
    # the packaged app runs speech recognition on the CPU.
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "piper", "nvidia"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Ash",
    icon=str(BUILD / "ash.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Ash", upx=False)
