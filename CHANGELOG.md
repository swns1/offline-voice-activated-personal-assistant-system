# Changelog

## Unreleased (planned as 1.0.0)

### Desktop app

- **A desktop window** (PySide6) with four tabs:
  - **Chat:** type to Ash. Yes/No buttons for confirmations. You can
    show replies without speaking them, and switch the microphone off
    completely.
  - **What can I say:** generated from the command list.
  - **Settings:** saved into `config.yaml` with its comments kept.
  - **Privacy:** offline mode, a switch per online feature, what's
    stored, the network log, and export and delete buttons.
- **A tray icon** whose colour shows whether Ash is listening.
  Closing the window keeps Ash running in the tray.
- **Voice, typing and clicks all go through one command worker**, so
  they can't trip over each other. A question asked by voice can be
  answered with a click.
- **First start asks before downloading the speech models.** Both
  downloads are blocked in offline mode and recorded in the network log.
- **`--selftest`** loads every engine without speaking, listening or
  downloading. **`--console`** runs voice-only, as before.
- **A packaged Windows build** (`Ash.exe`, `scripts/build_release.py`),
  built and attached to a GitHub release when a version tag is pushed.
- **GitHub Actions** runs the tests and ruff on Windows for every push.
- **Measurement scripts:** `scripts/benchmark.py` for latency, broken
  down by stage, and `scripts/stt_accuracy.py` for speech-recognition
  accuracy on your own voice (word error rate and command accuracy, per
  Whisper model size).

### Everyday features

- Time, date and "what day is…" questions, answered offline.
- A calculator and unit conversions, offline (a safe evaluator, never
  `eval`).
- Weather from Open-Meteo, for a city you set (Ash never works out your
  location).
- Play, pause, skip and "what's playing" for any app, through Windows'
  media controls.
- Notes and lists ("add milk to my shopping list"), stored encrypted.
- Battery, storage, screenshots, brightness, and dark or light mode.
- Polite phrasing is understood ("could you open Spotify please").
- Every command is declared once, in the skill catalog.

### Privacy (designed in line with the Philippine Data Privacy Act of 2012)

- Personal data is encrypted at rest with Windows DPAPI.
- Logs don't record what you say, and are deleted after 7 days.
- Every request that leaves the PC goes through one gate. It's
  checked against offline mode and your consent, and logged.
- Online features are asked about once, at startup, saying what each
  one sends and to whom.
- "What data do you have", "export my data", "delete my voiceprint" and
  "delete all my data", by voice or in the window.
- A privacy assessment: [docs/PRIVACY.md](docs/PRIVACY.md).

### Fixes

- A startup crash: the winrt packages' bundled C++ runtime stopped the
  wake-word engine from loading.
- Ash no longer contacts Hugging Face on every start.
- Spoken "Yes." now confirms. Routines can no longer skip a
  confirmation. A single shared word no longer counts as an app match.
- One failing command no longer stops Ash.

## 0.1.0 (September 2026)

The voice assistant before this round of work:
- the wake word and offline speech recognition
- opening apps and games
- timers, reminders and routines
- the Outlook calendar
- Spotify
- volume and power
- DuckDuckGo answers
- conversation, screen understanding and memory through a local Ollama model
- on-screen text by OCR
- guided clicking and typing
- barge-in, a tray icon, autostart, and a mute hotkey
