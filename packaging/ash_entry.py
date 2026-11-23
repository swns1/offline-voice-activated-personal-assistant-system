"""Entry point for the packaged Ash.exe (PyInstaller runs a script, not
`python -m ash`). Same flags: Ash.exe --console, Ash.exe --minimized."""
from ash.main import main

if __name__ == "__main__":
    main()
