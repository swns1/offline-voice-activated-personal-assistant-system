"""Notes and lists, kept on this PC and encrypted at rest
(ash/privacy/secure_store.py) -- listed in the data inventory, so
they're included in "what data do you have", "export my data" and
"delete all my data".

- "take a note: buy flowers for mom" / "read my notes" / "delete my notes"
- "add milk and eggs to my shopping list" / "what's on my shopping list"
  / "remove milk from my shopping list" / "clear my shopping list" /
  "what lists do I have"
"""
import logging
import re
import threading
from datetime import datetime

from rapidfuzz import fuzz, process

from ash.actions.confirmation import ask_to_confirm
from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.privacy import secure_store
from ash.registry.schema import Registry
from ash.utils.paths import NOTES_PATH

_READ_LIMIT = 5
_ITEM_MATCH_CUTOFF = 80.0
_lock = threading.Lock()

_ADD_RE = re.compile(r"^(?P<items>.+?)\s+(?:to|on|onto)\s+(?:my\s+|the\s+)?(?P<list>[\w' ]+?)\s+list$")
_REMOVE_RE = re.compile(r"^(?P<items>.+?)\s+(?:from|off|off of)\s+(?:my\s+|the\s+)?(?P<list>[\w' ]+?)\s+list$")
_LIST_NAME_RE = re.compile(r"^(?:my\s+|the\s+)?(?P<list>[\w' ]+?)\s+list$")


# --- storage ---------------------------------------------------------------------

def _load() -> dict:
    try:
        data = secure_store.read_json(NOTES_PATH, default={})
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("notes", [])
    data.setdefault("lists", {})
    return data


def _save(data: dict) -> None:
    try:
        secure_store.write_json(NOTES_PATH, data)
    except OSError:
        pass  # best-effort, like the rest of Ash's persistence


def _list_key(name: str) -> str:
    """"to do", "to-do" and "todo" are the same list."""
    return re.sub(r"[\s'-]", "", name.lower())


def _find_list(lists: dict, name: str) -> str | None:
    key = _list_key(name)
    return next((existing for existing in lists if _list_key(existing) == key), None)


def _split_items(text: str) -> list[str]:
    parts = re.split(r",\s*|\s+and\s+", text.strip())
    return [re.sub(r"^(some|a|an)\s+", "", p).strip() for p in parts if p.strip()]


def _spoken_list(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _display_name(name: str) -> str:
    return "to-do" if _list_key(name) == "todo" else name


# --- notes --------------------------------------------------------------------------

def handle_note_add(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    text = re.sub(r"^(that|of)\s+", "", target.strip())
    if not text:
        tts.say("What should the note say?")
        return HandlerResult()
    with _lock:
        data = _load()
        data["notes"].append({"text": text, "at": datetime.now().isoformat(timespec="seconds")})
        _save(data)
    log.info("Saved a note (%d stored)", len(data["notes"]))
    tts.say(f"Noted: {text}.")
    return HandlerResult()


def handle_note_read(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    notes = _load()["notes"]
    if not notes:
        tts.say("You don't have any notes.")
        return HandlerResult()
    newest = [n["text"] for n in reversed(notes)][:_READ_LIMIT]
    intro = f"You have {len(notes)} note{'' if len(notes) == 1 else 's'}."
    if len(notes) > _READ_LIMIT:
        intro += f" Here are the latest {_READ_LIMIT}."
    tts.say(intro + " " + " ".join(f"{text[0].upper()}{text[1:].rstrip('.')}." for text in newest))
    return HandlerResult()


def handle_note_clear(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    count = len(_load()["notes"])
    if not count:
        tts.say("You don't have any notes to delete.")
        return HandlerResult()

    def clear() -> HandlerResult:
        with _lock:
            data = _load()
            data["notes"] = []
            _save(data)
        log.info("Deleted all notes")
        tts.say("Your notes are deleted.")
        return HandlerResult()

    return ask_to_confirm(
        f"This permanently deletes all {count} of your notes. Are you sure?" if count > 1
        else "This permanently deletes your note. Are you sure?",
        clear, action="note_clear", declined_reply="Okay, I'll keep them.",
        tts=tts, log=log, config=config,
    )


# --- lists ---------------------------------------------------------------------------

def handle_list_add(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    match = _ADD_RE.match(target.strip())
    if not match:
        # "add 5 and 3" is maths, not a list.
        from ash.actions.calculator import answer
        sum_answer = answer(re.sub(r"\s+and\s+", " plus ", target))
        if sum_answer:
            tts.say(sum_answer)
            return HandlerResult()
        tts.say("Which list? Try 'add milk to my shopping list'.")
        return HandlerResult()

    items = _split_items(match.group("items"))
    spoken_name = _display_name(match.group("list").strip())
    with _lock:
        data = _load()
        name = _find_list(data["lists"], spoken_name)
        is_new = name is None
        if is_new:
            name = spoken_name
            data["lists"][name] = []
        existing = {i.lower() for i in data["lists"][name]}
        added = [i for i in items if i.lower() not in existing]
        data["lists"][name].extend(added)
        _save(data)

    log.info("Added %d item(s) to a list", len(added))
    if not added:
        tts.say(f"{_spoken_list(items).capitalize()} {'is' if len(items) == 1 else 'are'} already on your {name} list.")
    elif is_new:
        tts.say(f"Added {_spoken_list(added)} to a new {name} list.")
    else:
        tts.say(f"Added {_spoken_list(added)} to your {name} list.")
    return HandlerResult()


def handle_list_read(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    match = _LIST_NAME_RE.match(target.strip())
    if not match:
        # "what's on my calendar tomorrow", "what's on my mind": not a list.
        if "calendar" in target or "schedule" in target:
            from ash.actions.calendar import handle_calendar_list
            return handle_calendar_list(target, registry, tts, log, config)
        if "screen" in target:
            from ash.actions.vision import handle_screen_describe
            return handle_screen_describe("", registry, tts, log, config)
        tts.say(f"I don't have a list called {target}.")
        return HandlerResult()

    lists = _load()["lists"]
    name = _find_list(lists, match.group("list"))
    if name is None:
        tts.say(f"You don't have a {match.group('list').strip()} list yet.")
    elif not lists[name]:
        tts.say(f"Your {name} list is empty.")
    else:
        items = lists[name]
        tts.say(f"Your {name} list has {len(items)} item{'' if len(items) == 1 else 's'}: {_spoken_list(items)}.")
    return HandlerResult()


def handle_list_remove(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    match = _REMOVE_RE.match(target.strip())
    if not match:
        tts.say("Which list? Try 'remove milk from my shopping list'.")
        return HandlerResult()

    with _lock:
        data = _load()
        name = _find_list(data["lists"], match.group("list"))
        if name is None:
            tts.say(f"You don't have a {match.group('list').strip()} list.")
            return HandlerResult()
        current = data["lists"][name]
        removed, missing = [], []
        for item in _split_items(match.group("items")):
            best = process.extractOne(item, current, scorer=fuzz.WRatio, score_cutoff=_ITEM_MATCH_CUTOFF) if current else None
            if best is None:
                missing.append(item)
            else:
                current.remove(best[0])
                removed.append(best[0])
        _save(data)

    log.info("Removed %d item(s) from a list", len(removed))
    parts = []
    if removed:
        parts.append(f"Removed {_spoken_list(removed)} from your {name} list.")
    if missing:
        parts.append(f"{_spoken_list(missing).capitalize()} {'isn' if len(missing) == 1 else 'aren'}'t on it.")
    tts.say(" ".join(parts))
    return HandlerResult()


def handle_list_clear(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    match = _LIST_NAME_RE.match(target.strip())
    lists = _load()["lists"]
    name = _find_list(lists, match.group("list")) if match else None
    if name is None:
        tts.say(f"You don't have a {match.group('list').strip() if match else target} list.")
        return HandlerResult()
    count = len(lists[name])

    def clear() -> HandlerResult:
        with _lock:
            data = _load()
            data["lists"].pop(_find_list(data["lists"], name) or name, None)
            _save(data)
        log.info("Deleted a list")
        tts.say(f"Your {name} list is deleted.")
        return HandlerResult()

    return ask_to_confirm(
        f"This deletes your {name} list and the {count} item{'' if count == 1 else 's'} on it. Are you sure?",
        clear, action="list_clear", declined_reply="Okay, I'll keep it.",
        tts=tts, log=log, config=config,
    )


def handle_lists_list(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    names = list(_load()["lists"])
    if not names:
        tts.say("You don't have any lists yet. Try 'add milk to my shopping list'.")
    else:
        tts.say(f"You have {len(names)} list{'' if len(names) == 1 else 's'}: {_spoken_list(names)}.")
    return HandlerResult()
