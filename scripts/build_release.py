r"""Build the Windows release: dist/Ash/ (Ash.exe and everything it
needs) and dist/Ash-<version>-windows.zip.

Run: .venv\Scripts\python.exe scripts\build_release.py
Needs PyInstaller (pip install pyinstaller). Takes a few minutes.
"""
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
DIST = ROOT / "dist"


def version() -> str:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def make_icon(path: Path) -> None:
    """The same blue "A" as the window's icon (ash/gui/icon.py), as a .ico."""
    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = int(size * 0.06)
    draw.ellipse((margin, margin, size - margin, size - margin), fill=(37, 99, 235, 255))
    try:
        font = ImageFont.truetype("segoeuib.ttf", int(size * 0.55))
    except OSError:
        font = ImageFont.load_default()
    draw.text((size / 2, size / 2), "A", font=font, fill="white", anchor="mm")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def main() -> None:
    make_icon(BUILD / "ash.ico")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"),
                    str(ROOT / "packaging" / "ash.spec")], check=True)

    app = DIST / "Ash"
    # Never ship files generated on the build machine.
    for generated in [app / "_internal" / "config" / "registry.auto.yaml"]:
        generated.unlink(missing_ok=True)

    archive = DIST / f"Ash-{version()}-windows.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file in sorted(app.rglob("*")):
            if file.is_file():
                zf.write(file, Path("Ash") / file.relative_to(app))
    size_mb = archive.stat().st_size / 1024 ** 2
    print(f"Built {archive} ({size_mb:.0f} MB)")


if __name__ == "__main__":
    main()
