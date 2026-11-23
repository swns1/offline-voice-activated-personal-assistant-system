"""Finding your files, offline.

- "find my resume": searches file names with the Windows Search index
  (the same index File Explorer's search box uses; it lives on this PC
  and answers instantly). Only your own user folder, never AppData
  (program data, caches) or other people's folders. Says the newest
  match and offers to open it.
- "open my latest download": the newest file in your Downloads folder,
  after asking. Programs and scripts are never opened by voice -- a
  download is the classic way malware arrives -- Ash shows them in File
  Explorer instead, for you to decide.

Nothing is stored, and what you searched for isn't logged.
"""
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from ash.actions.clock import spoken_date
from ash.actions.results import YES_NO, HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.privacy.redact import said
from ash.registry.schema import Registry

_LIMIT = 5
# Words that describe the search rather than the file's name.
_FILLER = {"my", "the", "a", "an", "file", "files", "document", "documents", "doc", "called", "named",
           "for", "me", "please", "of", "that", "this", "where", "is", "are", "i", "saved"}
# Never opened by voice, wherever they came from: they run code.
RUNNABLE = {".exe", ".msi", ".msix", ".appx", ".bat", ".cmd", ".com", ".ps1", ".vbs", ".vbe", ".js", ".jse",
            ".wsf", ".wsh", ".scr", ".pif", ".lnk", ".reg", ".hta", ".jar", ".py", ".iso", ".img"}


@dataclass(frozen=True)
class FoundFile:
    path: Path
    modified: datetime


def search_words(target: str) -> list[str]:
    words = re.findall(r"[\w\-]+", target.lower())
    meaningful = [w for w in words if w not in _FILLER]
    return meaningful or words


def _sql_literal(word: str) -> str:
    return re.sub(r"[^\w\-]", "", word)  # no quotes or wildcards from what you said


def build_query(words: list[str], home: Path, limit: int = _LIMIT) -> str:
    name_matches = " AND ".join(f"System.FileName LIKE '%{_sql_literal(w)}%'" for w in words)
    appdata = str(home / "AppData")
    return (
        f"SELECT TOP {limit} System.ItemPathDisplay, System.DateModified FROM SYSTEMINDEX "
        f"WHERE SCOPE='file:{home.as_posix()}' AND {name_matches} "
        f"AND System.ItemType <> 'Directory' AND NOT System.ItemPathDisplay LIKE '{appdata}%' "
        "ORDER BY System.DateModified DESC"
    )


def _local(moment) -> datetime:
    """The index reports times in UTC."""
    if getattr(moment, "tzinfo", None) is not None:
        return moment.astimezone().replace(tzinfo=None)
    return datetime(moment.year, moment.month, moment.day, moment.hour, moment.minute)


def search_index(words: list[str], home: Path | None = None, limit: int = _LIMIT) -> list[FoundFile]:
    """Raises if Windows Search isn't available."""
    import pythoncom
    import win32com.client

    home = home or Path.home()
    pythoncom.CoInitialize()
    try:
        connection = win32com.client.Dispatch("ADODB.Connection")
        connection.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
        records = win32com.client.Dispatch("ADODB.Recordset")
        records.Open(build_query(words, home, limit), connection)
        found = []
        while not records.EOF:
            found.append(FoundFile(Path(records.Fields.Item("System.ItemPathDisplay").Value),
                                   _local(records.Fields.Item("System.DateModified").Value)))
            records.MoveNext()
        records.Close()
        connection.Close()
        return found
    finally:
        pythoncom.CoUninitialize()


def _downloads_dir() -> Path:
    try:
        from win32com.shell import shell, shellcon
        return Path(shell.SHGetKnownFolderPath(shellcon.FOLDERID_Downloads))
    except Exception:
        return Path.home() / "Downloads"


def latest_download(folder: Path | None = None) -> FoundFile | None:
    folder = folder or _downloads_dir()
    newest = None
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return None
    for entry in entries:
        # Skip folders, hidden files and unfinished browser downloads.
        if not entry.is_file() or entry.name.startswith(".") or entry.name.endswith((".crdownload", ".part", ".tmp")):
            continue
        modified = datetime.fromtimestamp(entry.stat().st_mtime)
        if newest is None or modified > newest.modified:
            newest = FoundFile(Path(entry.path), modified)
    return newest


# --- saying it ------------------------------------------------------------------------

def where(path: Path, home: Path | None = None) -> str:
    """"in Documents, Jobs" -- the folder, relative to your user folder."""
    home = home or Path.home()
    try:
        parts = path.parent.relative_to(home).parts
    except ValueError:
        parts = path.parent.parts[1:]
    return "in " + ", ".join(parts[-2:]) if parts else "in your user folder"


def when(moment: datetime, today: date | None = None) -> str:
    today = today or date.today()
    days = (today - moment.date()).days
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    return f"on {spoken_date(moment.date(), today)}"


def _open(path: Path) -> None:
    os.startfile(path)


def _show_in_explorer(path: Path) -> None:
    subprocess.Popen(["explorer", f"/select,{path}"])


def _offer_to_open(found: FoundFile, intro: str, tts: TtsWorker, log: logging.Logger) -> HandlerResult:
    if found.path.suffix.lower() in RUNNABLE:
        tts.say(f"{intro} It's a program or script, so I won't open it by voice. "
                "I'll show it in File Explorer, and you can decide.")
        _show_in_explorer(found.path)
        return HandlerResult()

    def resume(answer: str) -> HandlerResult:
        from ash.actions.confirmation import is_affirmative

        if not is_affirmative(answer):
            tts.say("Okay.")
            return HandlerResult()
        try:
            _open(found.path)
        except OSError:
            log.warning("Couldn't open a found file", exc_info=True)
            tts.say("I couldn't open it.")
            return HandlerResult()
        log.info("Opened a found file")
        tts.say("Opening it.")
        return HandlerResult()

    return HandlerResult(done=False, question=f"{intro} Open it?", resume=resume, choices=YES_NO)


# --- handlers ---------------------------------------------------------------------------

def handle_find_file(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger,
                     config: Config) -> HandlerResult:
    words = search_words(target)
    if not words:
        tts.say("What file should I look for? Say, for example, 'find my resume'.")
        return HandlerResult()
    try:
        found = search_index(words)
    except Exception:
        log.warning("Windows Search query failed", exc_info=True)
        tts.say("I can't search your files right now. Windows Search may be turned off.")
        return HandlerResult()
    log.info("File search for %s: %d found", said(" ".join(words)), len(found))
    if not found:
        tts.say(f"I couldn't find a file called {' '.join(words)} in your folders.")
        return HandlerResult()

    newest = found[0]
    description = f"{newest.path.name} {where(newest.path)}, changed {when(newest.modified)}."
    if len(found) == 1:
        intro = f"I found {description}"
    else:
        others = ", ".join(f.path.name for f in found[1:3])
        count = f"at least {len(found)}" if len(found) == _LIMIT else str(len(found))
        more = f"I found {count} files. The newest is {description}"
        intro = f"{more} Others include {others}."
    return _offer_to_open(newest, intro, tts, log)


def handle_latest_download(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger,
                           config: Config) -> HandlerResult:
    newest = latest_download()
    if newest is None:
        tts.say("Your Downloads folder is empty.")
        return HandlerResult()
    return _offer_to_open(newest, f"Your latest download is {newest.path.name}, downloaded {when(newest.modified)}.",
                          tts, log)
