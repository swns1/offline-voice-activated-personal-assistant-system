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
Spotify commands), and your own local Ollama server on this PC (only
if it's installed — see "Local AI" below) — never anything else, and
never your files. Calendar access (if
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

A tray icon appears (right-click for "Open logs folder" / "Quit Ash") —
this is the normal way to stop Ash instead of Ctrl+C once it's not
running in a visible console (see "Run at login" below). Set
`tray.enabled: false` in `config/config.yaml` to turn it off.

Speak the configured wake word (`hey_jarvis` by default — see
`config/config.yaml`), then a command such as "open notepad" or "what
is the Eiffel Tower".

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

Ash is otherwise 100% reactive — it never speaks unless spoken to.
Setting `calendar.proactive_reminders: true` (needs `calendar.enabled:
true` too) is the one deliberate exception: it checks your calendar in
the background and speaks + shows a toast a few minutes before a
meeting starts, unprompted. Each meeting is only ever announced once.
Tune how far ahead and how often it checks with
`calendar.proactive_lookahead_minutes` (default 5) and
`calendar.proactive_poll_seconds` (default 60). Off by default — this
is the one feature where Ash initiates speech on its own, so it's worth
turning on deliberately rather than defaulting into it.

## System control

- Volume: "volume up" / "volume down" / "set the volume to 50" / "mute" / "unmute"
- Windows: "close discord" force-quits the app — so it first says what
  will be closed and that anything unsaved in it will be lost, and asks
  "are you sure?" (if the name matches several different programs, it
  names each one). "close this window" / "minimize this window" act on
  whatever's currently focused; closing a window this way is a normal
  close, so the app can still ask you to save.
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
  timers — see the commented example in that file). A risky step in a
  routine (e.g. shut down) still asks first, exactly as if you'd said it.
- Power: "lock my computer", "go to sleep", "shut down". Lock and sleep
  happen right away (nothing is lost). Shut down first explains that all
  your apps will close and anything unsaved will be lost, then asks "are
  you sure?" — only a clear yes ("yes", "yeah", "sure", "go ahead", ...)
  goes ahead; anything else, or no answer, cancels.
- Diagnostics: "are you working" / "run diagnostics" checks the
  microphone, whether Ollama is running (and has its model downloaded),
  and, if enabled, whether Spotify is connected
  — also available standalone via `scripts\selftest.py`, no need to
  talk to Ash for it.

### Voice-verified confirmation (optional)

By default, confirming a risky action (shutting down, force-closing an
app, clicking/typing on screen) just needs a spoken "yes" — anyone in
earshot. Set
`security.voice_gate_enabled: true` for an extra check on top of that:
the confirmation itself has to sound like you, not just be an
affirmative word, checked against a voiceprint you enroll once:

```
.venv\Scripts\python.exe scripts\enroll_voice.py
```

Speak naturally for the few seconds it records (a sentence or two, not
just "yes" — a longer sample makes for a better reference). Worth being
upfront about what this actually is: a classical MFCC-similarity check,
not a trained deep speaker-embedding model (those need a `torch`-based
multi-GB install — the same tradeoff that already ruled out training a
real "Hey Ash" wake word, see below). Treat it as a soft additional
check appropriate for a single-user machine, not a strong biometric
guarantee — `security.voice_match_threshold` (default `0.85`) tunes how
strict it is. If nothing's enrolled, or the check can't run for any
reason, it fails open — you get the same plain yes/no you had before
turning this on, never a shutdown you can't confirm at all.

## Local AI (Ollama)

Anything you say that isn't a known command and doesn't match an app
gets asked to a local language model instead of "I'm not sure what you
mean" — no cloud, no account, runs entirely on your PC via
[Ollama](https://ollama.com):

1. Install Ollama (separate installer, not a pip package) from
   https://ollama.com — it runs as a local background server.
2. Pull a model: `ollama pull llama3.2` (a few GB, one-time).

That's it — no config change needed. With `ollama.enabled: auto` (the
default), Ash uses the local-AI features whenever Ollama is running with
that model downloaded, and quietly does without them when it isn't: it
just says "I'm not sure what you mean" as before. It re-checks every 30
seconds or so, so starting Ollama after Ash (e.g. both launching at
login) is picked up without a restart. Ash prints whether local AI is on
when it starts, and "run diagnostics" reports it too. Set
`ollama.enabled: true` or `false` to force it on or off instead.

Replies can take a few seconds on CPU — Ash says "Let me think" while it
waits. It
remembers the last few exchanges, so a follow-up like "what's its
population" after "what's the capital of France" works; say "stop" to
end the conversation early.

### Understanding phrasing that doesn't match a template

Ash's command parsing is a fixed set of phrase templates ("volume up",
"lock my computer", etc.) — fast and predictable, but it only recognizes
phrasing close to those templates. With local AI on (see above), anything
that doesn't match any template gets one extra check before falling
back to a conversational reply: the local model is asked whether it
actually means one of Ash's other commands. So "turn it down a bit" or
"shut this thing down" can still trigger `volume_down`/`shutdown` even
though neither is phrased like the literal template — while an actual
question or conversational remark just falls through to Local AI as
before. Adds a few seconds of latency (a second local model call) only
for utterances that didn't match a template in the first place; normal
commands are completely unaffected. Destructive actions still ask for
confirmation either way — this only decides *which* command was meant,
not whether it's safe to run.

### Persistent memory

"remember that I'm vegetarian" / "remember my dog's name is Rex" sticks
around across restarts (`%LOCALAPPDATA%\Ash\memory.json`) — unlike the
in-conversation history above, which resets every conversation. It's
automatically folded into every Local AI reply so it's used naturally
without having to ask; "what do you know about me" speaks everything
remembered, and "forget that I'm vegetarian" / "forget everything"
removes it. This is plain local storage, so it works even without
Ollama — only the "used naturally in chat" half needs local AI.

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

### Reading exact on-screen text

"read my screen" / "read the screen" / "what does my screen say" reads
back the *exact* text on screen via local OCR — error codes, table
values, anything where an exact string matters more than a general
description. This is a different, more literal tool than "what's on my
screen"/"describe my screen" above, which asks the vision model for a
looser prose description instead; use whichever fits what you're
after. Needs the free [Tesseract OCR
engine](https://github.com/UB-Mannheim/tesseract/wiki) installed
separately (a Windows installer, not a pip package — like Ollama), and
adds itself to your PATH during setup. No Ollama needed — this runs
fully offline with no model, so it works even without Ollama set up at
all. Very long on-screen text is cut short with a spoken note
rather than read in full.

### Guided desktop actions (optional, off by default)

"click Save" / "click the OK button" / "type my email address" let Ash
actually operate your desktop, not just read it — Ash's version of the
"computer use" pattern. It works by locating the exact text via the
same OCR as above (needs Tesseract installed, see above), fuzzy-matched
against what's visible, then moving the mouse and clicking, or typing
wherever focus currently is. Set `desktop_control.enabled: true` in
`config/config.yaml` to turn it on — off by default, deliberately more
guarded than every other integration in this project, since it's the
one feature that directly manipulates your PC:

- Every single click/type says exactly what it's about to do and asks
  first — "I'll move your mouse and click 'Save' on your screen. Are you
  sure?" / "I'll type 'hello' into whichever window is active right now.
  Are you sure?" — naming exactly what it found, not a generic yes/no. With `security.voice_gate_enabled` (see "Voice-verified
  confirmation" above) also on, that confirmation needs to match your
  enrolled voice too.
- Text-label only: it can click a labeled button or menu item, not a
  bare icon — that's an intentional scope limit, not a bug.
- If two on-screen elements share the exact same label, only one is
  targetable right now — there's no disambiguation prompt for this yet.
- **Known limitation**: this hasn't been verified on a Windows display
  running at non-100% scaling (125%/150%) — the screenshot's pixel
  coordinates and the actual click coordinates could disagree there.
  If clicks land in the wrong place, that's the first thing to check.

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

## Run at login, mute hotkey, and a custom wake word

**Autostart**: set `autostart: true` in `config/config.yaml` and restart
Ash once — it adds itself to your per-user Windows Registry Run key,
launching via `pythonw.exe` (no console window) from then on. Applied
automatically on every startup (so toggling the config value and
restarting Ash is enough), or run
`.venv\Scripts\python.exe scripts\apply_autostart.py` to apply it
without starting the full assistant. No admin rights needed (it's a
per-user, not machine-wide, registry key).

**Mute hotkey**: `hotkey.toggle_mute` (default `ctrl+alt+m`) toggles
mute from anywhere, without needing to be talking to Ash — set it to
`null` to disable. Heads up: this uses the `keyboard` package's global
hook, which is known to sometimes need Administrator privileges to
actually receive keypresses on some Windows setups even though
registering it never errors either way — if the hotkey doesn't respond,
try running Ash as Administrator.

**A real "Hey Ash" wake word**: Ash ships with openWakeWord's
pretrained `hey_jarvis` model as a stand-in — training an actual "Hey
Ash" model needs openWakeWord's own training pipeline (`torch`,
`torchaudio`, `speechbrain`, and multi-GB datasets — a genuinely heavy,
separate undertaking, not something this project installs or runs for
you). See openWakeWord's own docs/training notebook
(https://github.com/dscripka/openWakeWord) for how to train one. Once
you have a trained `.onnx` file, point Ash at it directly:

```yaml
wake_word:
  keyword: models/hey_ash.onnx   # relative to the project folder, or an absolute path
```

## Configuration

- `config/config.yaml` — wake word, audio, browser, hotkey, tray,
  autostart, registry auto-rescan, voice-verified confirmation, guided
  desktop actions, Spotify, search, calendar, and Ollama settings.
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
`config/registry.auto.yaml`. Entries in `config/registry.yaml` always
take precedence over auto-discovered ones with the same name, so
hand-author an entry there if you need to override how something
launches.

You don't normally need to run this yourself: Ash rescans automatically
at every startup (`registry.auto_rescan_on_startup: true`, the default —
takes about a second), so a game downloaded since Ash last ran is
already voice-launchable the next time it starts. If you ask for
something by name while Ash is still running from before the download,
it also retries with a one-off rescan before giving up and saying it
doesn't know what you mean — so most of the time you can just ask,
restart or not. The script is there for forcing a rescan on demand, or
if you've set `auto_rescan_on_startup: false` to control it manually.

### How spoken app names are matched

"open X" (or launch/start/run/play X) matches X against app names
loosely — "open my elden ring game" finds Elden Ring, and small
speech-to-text slips like "spotfy" still work. If you just say a name
with no verb ("discord"), Ash only opens an app whose name closely
matches what you said; otherwise it treats it as conversation (local
AI) or says it's not sure. Either way, sharing a single word with an
app's name isn't enough — "turn it down a bit" won't open "Python
Module Docs (64-bit)" just because both contain "bit".

## Testing

```
.venv\Scripts\python.exe -m pytest
```
