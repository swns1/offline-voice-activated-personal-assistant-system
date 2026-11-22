"""Your data rights, as voice commands (and, in the GUI, buttons):

- "what data do you have": what Ash keeps about you right now, and that
  you can get a copy or erase it (RA 10173 Sec. 16(a), (c): the rights
  to be informed and to access).
- "export my data": a readable copy in your Documents folder (Sec. 18:
  data portability). Asks first, because the copy isn't encrypted.
- "delete my voiceprint" / "delete all my data": erase it (Sec. 16(e)).
  Asks first, saying exactly what will be lost.
- Correcting what's stored ("forget that I'm vegetarian") already
  exists in ash/actions/memory.py (Sec. 16(d)).

Everything here works from the single list in ash/privacy/inventory.py.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from ash.actions.confirmation import ask_to_confirm
from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.privacy import inventory
from ash.registry.schema import Registry


# --- what data do you have --------------------------------------------------

def handle_data_inventory(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    stored = [item for item in inventory.INVENTORY if item.erasable and inventory.is_stored(item)]
    if not stored:
        tts.say("I'm not keeping anything about you on this PC right now.")
        return HandlerResult()

    described = [_describe(item) for item in stored]
    listed = described[0] if len(described) == 1 else ", ".join(described[:-1]) + f", and {described[-1]}"
    reply = f"Here's what I keep on this PC: {listed}."
    unencrypted = [item for item in stored if not item.encrypted]
    if unencrypted:
        reply += " All of it is encrypted except the troubleshooting logs"
        reply += "." if config.privacy.log_transcripts else ", which don't include what you say."
    else:
        reply += " All of it is encrypted."
    reply += " Say 'export my data' for a copy, or 'delete all my data' to erase it."
    tts.say(reply)
    return HandlerResult()


def _describe(item: inventory.StoredData) -> str:
    contents = inventory.read_contents(item)
    if item.key == "memory" and isinstance(contents, dict):
        n = len(contents.get("facts") or [])
        return f"{n} remembered fact{'' if n == 1 else 's'}"
    if item.key == "timers" and isinstance(contents, list):
        n = len(contents)
        return f"{n} timer{'' if n == 1 else 's'} or reminder{'' if n == 1 else 's'}"
    if item.key == "network_log" and isinstance(contents, list):
        n = len(contents)
        return f"a log of {n} time{'' if n == 1 else 's'} I went online"
    return item.name


# --- export my data -----------------------------------------------------------

def _documents_dir() -> Path:
    """Your Documents folder, wherever Windows has it (e.g. moved to
    OneDrive)."""
    try:
        from win32com.shell import shell, shellcon
        return Path(shell.SHGetKnownFolderPath(shellcon.FOLDERID_Documents))
    except Exception:
        return Path.home() / "Documents"


def build_export() -> dict:
    items = []
    for item in inventory.INVENTORY:
        files = inventory.existing_files(item)
        entry = {
            "name": item.name,
            "purpose": item.purpose,
            "kept": item.kept,
            "encrypted_on_this_pc": item.encrypted,
            "sensitive": item.sensitive,
            "stored": bool(files),
            "files": [str(p) for p in files],
        }
        if files and item.exportable:
            entry["contents"] = inventory.read_contents(item)
        elif files and item.export_note:
            entry["note"] = item.export_note
        items.append(entry)
    return {
        "about": ("Everything Ash, your offline voice assistant, keeps on this PC, exported at your "
                  "request. This copy is NOT encrypted -- delete it when you no longer need it."),
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "items": items,
    }


def handle_export(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    def export() -> HandlerResult:
        folder = _documents_dir()
        path = folder / f"Ash data export {datetime.now():%Y-%m-%d %H%M}.json"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(build_export(), indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            log.exception("Data export failed")
            tts.say("I couldn't save the export file.")
            return HandlerResult()
        log.info("Exported your data to your Documents folder")
        tts.say(f"Saved it to your Documents folder as '{path.stem}'.")
        return HandlerResult()

    return ask_to_confirm(
        "I'll save a copy of the data I keep about you as a readable file in your Documents folder. "
        "Unlike the originals, that copy won't be encrypted, so anyone who can open your Documents "
        "folder could read it. Go ahead?",
        export, action="privacy_export", declined_reply="Okay, I won't export anything.",
        tts=tts, log=log, config=config,
    )


# --- delete my voiceprint -------------------------------------------------------

def handle_delete_voiceprint(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    item = inventory.by_key("voiceprint")
    if not inventory.is_stored(item):
        tts.say("You don't have a voiceprint saved.")
        return HandlerResult()

    def delete() -> HandlerResult:
        failed = _delete(item)
        if failed:
            tts.say("I couldn't delete your voiceprint.")
        else:
            log.info("Deleted your voiceprint")
            tts.say("Your voiceprint is deleted.")
        return HandlerResult()

    question = "This permanently deletes your voiceprint."
    if config.security.voice_gate_enabled:
        question += " Risky actions will go back to accepting a plain yes until you enroll again."
    return ask_to_confirm(
        question + " Are you sure?", delete, action="privacy_delete_voiceprint",
        declined_reply="Okay, I'll keep it.", tts=tts, log=log, config=config,
    )


# --- delete all my data ------------------------------------------------------------

def handle_delete_all(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    stored = [item for item in inventory.INVENTORY if item.erasable and inventory.is_stored(item)]
    if not stored:
        tts.say("I'm not keeping anything about you on this PC, so there's nothing to delete.")
        return HandlerResult()

    names = [item.name for item in stored]
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f", and {names[-1]}"

    def delete() -> HandlerResult:
        failed = delete_everything(log)
        if failed:
            tts.say(f"I deleted almost everything, but couldn't delete {', '.join(failed)}.")
        else:
            tts.say("Done. Everything I kept about you on this PC has been deleted.")
        return HandlerResult()

    return ask_to_confirm(
        f"This permanently deletes everything I keep about you on this PC: {listed}. "
        f"Pending reminders won't go off, and online features will ask for permission again. "
        f"This can't be undone. Are you sure?",
        delete, action="privacy_delete_all", declined_reply="Okay, I haven't deleted anything.",
        tts=tts, log=log, config=config,
    )


def delete_everything(log: logging.Logger) -> list[str]:
    """Erase every erasable item in the inventory. Returns the names of
    any that couldn't be deleted (empty if all went)."""
    from ash.actions import spotify, timers
    from ash.nlu import context
    from ash.utils.logging_setup import close_log_files

    log.info("Deleting all your data at your request")  # the last line before the logs go too
    timers.cancel_all(persist=False)  # stop pending reminders without rewriting their file
    spotify._client = None            # drop the signed-in Spotify session
    context.clear()                   # "it"/"that" memory of your last app/search/song
    close_log_files(log)

    failed = []
    for item in inventory.INVENTORY:
        if item.erasable and _delete(item):
            failed.append(item.name)
    return failed


def _delete(item: inventory.StoredData) -> bool:
    """Delete an item's files; True if any couldn't be deleted."""
    failed = False
    for path in inventory.existing_files(item):
        try:
            path.unlink()
        except OSError:
            failed = True
    return failed
