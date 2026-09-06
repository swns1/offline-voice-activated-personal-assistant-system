# Ash

A local, fully-offline, wake-word-activated voice assistant for Windows.

Say the wake word, speak a command, and Ash opens an app/game, answers
a question, controls Spotify, checks/adds to your calendar, adjusts the
volume, sets timers/reminders and routines, locks/sleeps/shuts down the
PC, or — for anything else — asks a local AI model. Transcription,
wake-word detection, and text-to-speech all run locally; nothing is
sent to a cloud API. The only network calls Ash ever makes are to
DuckDuckGo's free Instant Answer API (for "what is X"-style questions —
no account/key, can be turned off), Spotify's API (only if you use
Spotify commands), and your own local Ollama server (only if you enable
it) — never anything else, and never your files. Calendar access (if
enabled) talks to your local desktop Outlook install, not the network.

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
`config/config.yaml`), then a command such as "open notepad" or "what
is the Eiffel Tower". Ctrl+C to quit.

If a command is ambiguous (e.g. two similarly-named apps, or more than
one browser profile with none pinned in config), Ash asks a clarifying
follow-up question — no wake word needed for your answer, just speak it
within a few seconds.

Ash remembers the last app you opened, search you made, and Spotify
track you played, so "open discord" then "close it", or "search for
pizza" then "search that again", resolves "it"/"that"/"this" instead
of needing everything repeated. ("pause"/"resume"/"skip" already work
on whatever's currently playing without needing this — Spotify tracks
that itself.)

Say "stop" (or "cancel", "be quiet") anytime to interrupt whatever Ash
is currently saying — or just start talking over it (barge-in): if you
speak while Ash is mid-response, it stops and starts listening to what
you're saying instead, no wake word needed. This is plain VAD-based
speech detection with no acoustic echo cancellation, so on hardware
where the mic picks up the speakers directly (no headset, a laptop's
built-in mic sitting right next to its speakers), Ash's own voice can
occasionally trigger a false barge-in on itself. Set
`audio.barge_in_enabled: false` in `config/config.yaml` if that happens
on your setup.

## Search

"search for X" / "what is X" / "look up X" answers directly via
DuckDuckGo's free Instant Answer API (`search.enabled: true` in
`config/config.yaml`, on by default) — no account or key, but coverage
is patchy: great for named topics ("Eiffel Tower", "Python programming
language"), nothing for question-style phrasing, calculators, or
dictionary lookups. If it can't find an answer, it says so and suggests
the explicit browser-opening phrasing instead: "search in browser for
X" always opens a real search in your browser (with profile-picking, if
you have more than one), regardless of whether DuckDuckGo has anything.

## Calendar

Reads and adds to your local desktop Outlook calendar via COM — off by
default (`calendar.enabled: false`), and only works if Outlook itself is
installed and configured (no separate account setup needed on Ash's
side). "what's on my calendar" / "what's my next meeting" speaks what's
coming up in the next 24 hours; "add to my calendar team meeting at
3pm" always asks for confirmation with the actual details before
writing anything ("Add 'team meeting' to your calendar at 3pm?").

## System control

- Volume: "volume up" / "volume down" / "set the volume to 50" / "mute" / "unmute"
- Windows: "close discord" (closes the app), "close this window" /
  "minimize this window" (acts on whatever's currently focused)
- Timers: "set a timer for 5 minutes", "remind me at 3pm to call mom",
  "remind me every day at 8am to take medicine" (recurring — daily or
  "every weekday"), "cancel my timer", "list my timers" — timers survive
  a restart; if one should have fired while Ash was closed, it's
  announced as soon as Ash starts back up (a recurring one reschedules
  itself for its next occurrence). Alerts also show as a Windows
  notification, not just spoken.
- Routines: "run my `<name>` routine" runs a named sequence of steps you
  define under `routines:` in `config/registry.yaml` (e.g. a "good
  morning" routine that sets the volume, opens Spotify, and lists your
  timers — see the commented example in that file).
- Power: "lock my computer", "go to sleep", "shut down" (asks "are you
  sure?" before actually shutting down)
- Diagnostics: "are you working" / "run diagnostics" checks the
  microphone, and (if enabled) whether Ollama and Spotify are reachable
  — also available standalone via `scripts\selftest.py`, no need to
  talk to Ash for it.

## Local AI (Ollama)

Anything you say that isn't a known command and doesn't match an app
gets asked to a local language model instead of "I'm not sure what you
mean" — no cloud, no account, runs entirely on your PC via
[Ollama](https://ollama.com):

1. Install Ollama (separate installer, not a pip package) from
   https://ollama.com — it runs as a local background server.
2. Pull a model: `ollama pull llama3.2` (a few GB, one-time).
3. Set `ollama.enabled: true` in `config/config.yaml`.

Replies can take a few seconds on CPU — Ash says "Let me think" while it
waits. If Ollama isn't running, Ash says so instead of crashing. It
remembers the last few exchanges, so a follow-up like "what's its
population" after "what's the capital of France" works; say "stop" to
end the conversation early.

### Screen understanding

"what's on my screen" / "describe my screen" / "read my screen" takes
a screenshot and describes it; "look at my screen and tell me what
this error means" asks something specific instead of a general
description. Uses a separate model pull from your text model, since
`llama3.2` itself is text-only:

```
ollama pull llama3.2-vision
```

(or set `ollama.vision_model` in `config/config.yaml` to whatever
vision model you'd rather use, e.g. `moondream` for something lighter).

## Spotify

Playback control ("spotify play X", "pause", "skip", "what's playing")
needs a Spotify Developer Dashboard app:

1. Create an app at https://developer.spotify.com/dashboard, add a
   redirect URI (matching `spotify.redirect_uri` in `config/config.yaml`,
   default `http://127.0.0.1:8888/callback`).
2. Set `spotify.enabled: true` and `spotify.client_id` in
   `config/config.yaml`.
3. Export the app's client secret as an environment variable:
   `setx SPOTIPY_CLIENT_SECRET "..."` (new terminal needed after).

The first Spotify command opens a browser to authorize once; playback
control requires a Spotify Premium account.

## Configuration

- `config/config.yaml` — wake word, audio, browser, hotkey, Spotify, search, calendar, and Ollama settings.
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
