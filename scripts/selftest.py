"""Standalone health check -- prints the same checks the "run
diagnostics" voice command speaks, without needing to talk to Ash.

Run: .venv\\Scripts\\python.exe scripts\\selftest.py
"""
from ash.actions.diagnostics import run_diagnostics
from ash.config import load_config

if __name__ == "__main__":
    config = load_config()
    for name, ok, detail in run_diagnostics(config):
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")
