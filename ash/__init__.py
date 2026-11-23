"""Ash, an offline voice assistant for Windows.

Load onnxruntime (the wake-word and voice-activity models' engine)
before anything else. The winrt packages (media controls, toast
notifications) ship their own, older copy of the Microsoft C++ runtime
(msvcp140.dll); whichever copy loads first is the one the whole process
uses, and onnxruntime fails to start with the older one ("DLL load
failed ... A dynamic link library (DLL) initialization routine
failed"). winrt works fine with the newer copy. Guarded by
tests/test_startup_imports.py, which imports Ash in a fresh process.
"""
try:
    import onnxruntime  # noqa: F401
except ImportError:  # not installed: nothing to order
    pass
