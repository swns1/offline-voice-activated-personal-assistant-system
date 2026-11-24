# Changelog

## Unreleased (planned as 1.0.0)

### Integrations and AI

- **Email through Outlook:** "check my email" says the unread count and
  who the latest emails are from, never the messages themselves. "Email
  Anna saying I'm running late" says exactly who, which address and
  what, then asks before sending. Off by default.
- **Finding files** with the Windows Search index, offline: "find my
  resume". "Open my latest download" asks first, and never opens
  programs or scripts.
- **Translation** by the local AI, with a pronunciation for languages in
  other scripts.
- **An optional natural voice** (Piper, running on this PC), with the
  Windows voice as the fallback. It's not bundled, because Piper is
  GPL-licensed.
- **The local AI calls Ash's commands as tools** (Ollama's native tool
  calling), generated from the command list. This is used for loose
  phrasing and multi-step requests. Every call is validated, and
  confirmations still apply.
- **Speech recognition accuracy, measured and improved.** 50 recordings
  of a real user saying Ash's commands, run through each Whisper model
  size. Giving Whisper Ash's command words as hotwords cut the word
  error rate from 12.6% to 5.7%, and raised commands run correctly from
  86% to 94%, for about 0.1 s. Whisper small stays the default: the
  smaller models get about 1 command in 4 wrong.
- **Local AI tested with real Ollama** (RTX 4060):
  - Choosing commands now uses temperature 0. At the default, the same
    sentence picked different commands.
  - Every request uses one context size. Mixing sizes made Ollama reload
    the model, up to 47 s.
  - Ash warms the model up in the background at startup.
  - Loose phrasing: 12 of 16 right, about 2.5–3 s each. Multi-step
    requests: 3 of 3.
- **Translation uses Gemma 3 (4B) when it's downloaded.** It got 10 of
  10 test phrases right; llama3.2 got most non-European ones wrong.
  Gemma is unloaded a minute after use, to leave the graphics card to
  the main model. Translation is plain text now (as JSON, llama3.2
  returned empty Japanese), with a pronunciation for every language.
- Clearer descriptions for the screenshot and note commands. They're
  what the local AI reads when choosing a command.
- Wording found by the study now works: "what is …" for every "what's …"
  command, "goto sleep", "search browser for …", and "set the timer for …".

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
