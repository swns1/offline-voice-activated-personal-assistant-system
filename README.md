# Ash

A local, fully-offline, wake-word-activated voice assistant for Windows.

Say the wake word, speak a command, and Ash opens an app/game or searches
the web — transcription, wake-word detection, and text-to-speech all run
locally; nothing is sent to a cloud API.

## Setup

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python.exe scripts\download_wake_word_models.py
```

The last step is a one-time download of openWakeWord's pretrained model
files (wake-word + feature-extraction models). Ash checks for these at
startup and will tell you to run this if they're missing.

## Running

```
.venv\Scripts\python.exe -m ash
```

Speak the configured wake word (`hey_jarvis` by default — see
`config/config.yaml`), then a command such as "open notepad" or "search
for the weather". Ctrl+C to quit.

## Configuration

- `config/config.yaml` — wake word, audio, browser, and hotkey settings.
- `config/registry.yaml` — hand-authored app entries and the search
  intent. Plain installed apps don't need to be hand-added here — see
  "Building the app registry" below.

## Building the app registry

Ash can auto-discover installed apps instead of requiring every app to
be hand-added to `config/registry.yaml`:

```
.venv\Scripts\python.exe scripts\build_registry_auto.py
```

This scans the Start Menu and, if installed, your Steam library, writing
`config/registry.auto.yaml`. Re-run it after installing new apps/games.
Entries in `config/registry.yaml` always take precedence over
auto-discovered ones with the same name, so hand-author an entry there
if you need to override how something launches.

## Testing

```
.venv\Scripts\python.exe -m pytest
```
