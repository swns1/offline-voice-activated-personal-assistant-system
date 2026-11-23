# Ash privacy assessment

Ash is a voice assistant that runs on your own Windows PC. This
document covers:

- what personal data Ash handles
- where that data is stored and for how long
- what, if anything, leaves the PC
- how Ash's design maps to the principles of the **Philippine Data
  Privacy Act of 2012 (Republic Act No. 10173)**

**About the claims in this document.** Ash is a personal tool. It
processes only your own data, on your own computer, so you are both the
person the data is about and the person in control of it. This
document describes a design that follows RA 10173's principles. It does
not claim certified compliance.

Section numbers were checked against the text of RA 10173 as reproduced
on [lawphil.net](https://lawphil.net/statutes/repacts/ra2012/ra_10173_2012.html).
The official sources ([privacy.gov.ph](https://privacy.gov.ph/data-privacy-act/)
and the Official Gazette) refused automated access. Check against them
before relying on a citation.

## 1. What Ash stores

Everything below lives on this PC. Everything except the troubleshooting
logs and the installed-apps list is encrypted with Windows DPAPI
(`ash/privacy/secure_store.py`). This table mirrors
`ash/privacy/inventory.py`, which drives the "what data do you have",
"export my data" and "delete all my data" commands. Tests fail if Ash
writes a file under `%LOCALAPPDATA%\Ash` that the inventory doesn't
list, or if the inventory lists something this table doesn't.

| Data | Where (`%LOCALAPPDATA%\Ash\…`) | Why | Kept | Encrypted | In export | Erased by "delete all" |
|---|---|---|---|---|---|---|
| remembered facts | `memory.json` | facts you asked Ash to remember, used to personalize answers | until you ask Ash to forget them | yes | yes | yes |
| notes and lists | `notes.json` | notes you dictate, and lists like your shopping list | until you delete them | yes | yes | yes |
| your city | `preferences.json` | the weather where you live (you tell Ash; it never works out your location) | until you change or delete it ("forget my city") | yes | yes | yes |
| timers and reminders | `timers.json` | so pending timers and reminders survive a restart | until they go off or you cancel them | yes | yes | yes |
| your voiceprint | `voiceprint.json` | checking it's really you before risky actions (only if voice-verified confirmation is on) | until you delete it | yes | listed only (biometric) | yes |
| your Spotify login | `.spotify_cache` | controlling Spotify without signing in every time | until you delete it | yes | listed only (a secret) | yes |
| your privacy choices | `privacy_state.json` | which online features you allowed, and offline mode | until you change or delete them | yes | yes | yes |
| the network log | `network_log.json` | a record of when and where Ash went online, so you can check | 30 days | yes | yes | yes |
| troubleshooting logs | `logs\ash.log*` | diagnosing problems; by default they don't contain what you say | `privacy.log_retention_days` (default 7) | no | listed only | yes |
| the list of installed apps | `registry.auto.yaml` in Ash's config folder | knowing which apps you can open by voice | rebuilt at every start | no | no | no (not about you) |

RA 10173 doesn't list biometric data as "sensitive personal
information" in Sec. 3(l). Ash still treats the voiceprint as the most
sensitive thing it stores:

- it's encrypted
- it's never copied into an export
- you can delete it on its own ("delete my voiceprint")
- it's only created if you run `scripts\enroll_voice.py` yourself

### What Ash handles but never stores

- **Audio.** Microphone audio is processed in memory and never written
  to disk.
- **Conversations with the local AI.** The last few exchanges are kept
  in memory for follow-up questions. They're gone when the conversation
  ends or Ash closes.
- **Screenshots** (for "what's on my screen" or "click Save") are taken
  in memory and sent only to the local OCR engine or the local AI
  model.
- **Calendar and email** are read live from Outlook when you ask, and
  never copied.
- **File searches.** "find my …" asks Windows' own search index on
  this PC, within your user folder only (never AppData). What you
  searched for isn't logged, and results aren't kept.
- **The chat in the desktop window.** What you type and what Ash
  replies is shown on screen only, and is gone when Ash closes. Typed
  commands follow the same logging rule as spoken ones.

## 2. What leaves this PC

Every HTTP request Ash makes goes through one module,
`ash/privacy/egress.py`. `tests/test_egress.py` fails if any other
module imports the HTTP library. The gate works like this:

- Requests to this PC itself (a local Ollama server) are always
  allowed, because nothing leaves the machine.
- Everything else must belong to a declared online feature, and may
  only go to that feature's declared websites.
- **Offline mode** ("go offline") blocks all of it.
- A feature you haven't allowed is blocked.
- Every request that does leave is written to the encrypted network
  log. Each entry records when, which feature, which website, and what
  *kind* of data was sent, never the content itself.

| Online feature | Sends | To | When | Your control |
|---|---|---|---|---|
| web search | the words you search for | DuckDuckGo (`api.duckduckgo.com`) | "what is …" / "search for …" | asked at first start; "allow / stop allowing web search"; offline mode |
| Spotify | the songs you ask for and your playback commands | Spotify (`api.spotify.com`, `accounts.spotify.com`) | Spotify commands, if you've set Spotify up | asked at the first start after you set it up; "allow / stop allowing Spotify"; offline mode |
| weather | the name of your city once, then its map coordinates — never your exact location | Open-Meteo (`geocoding-api.open-meteo.com`, `api.open-meteo.com`) | weather questions, and "my city is …" | asked at the first start after you set your city; "allow / stop allowing weather"; offline mode |
| the AI server | what you say to the AI, and screenshots when you ask about your screen | your Ollama server, **only if you configure one on another machine** | AI replies | your Ollama settings; offline mode |
| model downloads | requests for Ash's speech models (nothing about you) | GitHub and Hugging Face (`github.com` for the wake-word model, `huggingface.co` for the speech-recognition model) | **once**, when Ash is set up; the desktop window asks first | offline mode |

**Spotify** uses its own library's HTTP calls, which can't pass through
the gate. Each Spotify command checks permission in the same way and
is logged per command instead.

**The speech model.** faster-whisper's loader used to contact
huggingface.co on *every* start to check for a newer model version.
Measured on this codebase: two requests per start, neither of them
gated or logged. Ash now loads the downloaded model with
`local_files_only=True`. Only the one-time first download goes online,
and it's logged and blocked by offline mode.

### Outside Ash's gate (disclosed for completeness)

- **One-time setup.** You run these yourself, following the README:
  - `pip install` downloads Python packages from PyPI
  - `scripts\download_wake_word_models.py` downloads openWakeWord's
    models (it goes through the same check as the window's first-run
    download: blocked in offline mode, and logged)
  - `ollama pull` downloads AI models (Ollama is a separate program)
- **"search in browser for …"** opens your web browser on a search
  page. From there your browser's own privacy settings apply.
- **Outlook** syncs with your mail provider according to Outlook's own
  settings. Ash reads your calendar and inbox locally (for email: only
  the sender and subject of the latest few, never the message). It asks
  before adding a calendar event or sending an email, saying exactly
  what will be sent and to whom; Outlook then sends it over your mail
  account. Neither addresses nor message text are stored or logged.
- Once data reaches DuckDuckGo, Spotify, Open-Meteo, GitHub or Hugging
  Face, their privacy policies apply.

## 3. Mapping to RA 10173

| Provision | What it requires (paraphrased) | How Ash does it |
|---|---|---|
| Sec. 11: general principles | **Transparency**, **legitimate purpose**, **proportionality** | This document. Ash prints whether local AI is on at startup. Each consent question says what would be sent, to whom, and why. The network log and "what have you sent online" show what actually happened. Each stored item and online feature declares its purpose in code (`inventory.py`, `egress.py`). |
| Sec. 11 (proportionality) | Collect only what the purpose needs | Logs hide what you say by default (`<4 words hidden>`). Typed text and remembered facts are never logged. Web search sends only your search words. Audio is never stored. |
| Sec. 11(e) | Keep data only as long as necessary | Logs: 7 days by default. Network log: 30 days. Timers: until they go off. Everything else: until you delete it. |
| Sec. 3(b), Sec. 12(a) | Consent: freely given, specific, informed | Asked per feature once, when Ash first starts (or the first start after you set a feature up), saying what is sent, to whom, and why. If you don't answer, nothing is sent and Ash asks again later. Remembered with a timestamp. A "no" is respected and not asked again. You can withdraw any time. |
| Sec. 16(a), (b) | Right to be informed, including purposes, recipients and how long data is kept | "what data do you have". The inventory's purpose and retention for each item. This document. |
| Sec. 16(c) | Right to reasonable access | "what data do you have"; "export my data". The window's Privacy tab shows the same inventory (whether each item is stored right now, its size, and whether it's encrypted) and the full network log. |
| Sec. 16(d) | Right to correct errors | "forget that …", then remember the corrected fact. |
| Sec. 16(e) | Right to suspend, withdraw, block, remove or destroy | "stop allowing …"; offline mode; "delete my voiceprint"; "delete all my data". In the window: one click per feature (withdrawing asks nothing; allowing shows the same explanation as the spoken question), an offline switch, and delete buttons that ask first. |
| Sec. 16(f) | Right to damages | A legal remedy, not a software feature. Not applicable. |
| Sec. 18 | Right to a copy in a structured, commonly used electronic format | "export my data" writes JSON to your Documents folder. It warns first that the copy isn't encrypted. Secrets and the voiceprint are listed but not copied. |
| Sec. 20(a) | Reasonable organizational, physical and technical security measures | DPAPI encryption at rest. Atomic writes. One audited path out of the PC, enforced by a test. Confirmation (and optional voice match) before risky actions, export and deletion. |

## 4. Threat model

**Ash protects against:**

- **Other Windows accounts on this PC, and anyone who copies the files
  off it.** DPAPI ties the encryption key to your Windows login, so the
  copied files are unreadable elsewhere.
- **Your words leaking into log files.** Content is hidden by default
  and logs are deleted after the retention period.
- **Silent network traffic, including from future code changes.** There
  is a single gate out of the PC, a test enforces it, every request
  must belong to a declared feature with declared websites, and every
  request is logged.
- **Someone else confirming a risky action out loud.** This only
  applies if voice-verified confirmation is on.

**Ash does not protect against:**

- **Malware running as you.** It can call DPAPI just as Ash does. The
  app-specific entropy raises the bar slightly but isn't a defence.
- **Someone with your Windows password,** or who uses your PC while
  you're logged in. They can ask Ash "what data do you have". Export
  and deletion ask for confirmation first, and need your voice only if
  voice-verified confirmation is on.
- **People nearby hearing Ash's spoken replies.**
- **The export file.** It's unencrypted on purpose, so you can read it,
  and Ash tells you so.
- **Typed or clicked answers bypass the voiceprint check.** In the
  desktop window you can answer "Are you sure?" with a click. The voice
  check exists to stop another voice in the room from confirming; the
  keyboard and mouse are already behind your Windows sign-in, the same
  boundary DPAPI relies on.
- **The voiceprint check as a security boundary.** It's a classical
  MFCC-similarity check, a soft extra check rather than strong
  biometrics (see the README).

## 5. How to verify this yourself

- **Encryption.** Open any file in `%LOCALAPPDATA%\Ash` other than
  `logs`. Each starts with `ASH-DPAPI-1` followed by binary data, with
  no readable text.
- **What went online.** Say "what have you sent online". Say "go
  offline" and try a web search, which should be refused.
- **Logs.** Open `%LOCALAPPDATA%\Ash\logs\ash.log`. What you said
  appears as `<N words hidden>`.
- **Tests.** Run `.venv\Scripts\python.exe -m pytest`. In particular:
  - `tests/test_egress.py`: only the gate imports the HTTP library;
    offline mode and missing consent send nothing
  - `tests/test_privacy_rights.py`: every stored file is in the
    inventory, and delete-all leaves nothing behind
  - `tests/test_secure_store.py`: no readable text on disk
  - `tests/test_log_privacy.py`: typed text and remembered facts never
    reach the logs
  - `tests/test_stt_loading.py`: the speech model loads without going
    online

## 6. Known gaps

- The troubleshooting logs aren't encrypted, so that you can open them
  directly. By default they contain no content.
- If offline mode is on and the speech model has never been
  downloaded, Ash can't start. It prints how to turn offline mode off
  for that one download.
- Changing settings and viewing the network log are voice-only for now.
  The planned desktop app adds a privacy dashboard.
