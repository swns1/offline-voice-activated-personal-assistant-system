"""Finding files (ash/actions/files.py), with the search index faked."""
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from ash.actions import files
from ash.actions.dispatcher import dispatch
from ash.actions.results import YES_NO
from ash.config import Config
from ash.registry.schema import Registry

log = logging.getLogger("test")
HOME = Path(r"C:\Users\me")


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


def _run(text):
    tts = FakeTts()
    return tts, dispatch(text, Registry(), tts, log, Config())


@pytest.fixture
def index(monkeypatch):
    state = {"results": [], "searched": [], "opened": [], "shown": []}

    def search(words, home=None, limit=5):
        state["searched"].append(words)
        return state["results"]
    monkeypatch.setattr(files, "search_index", search)
    monkeypatch.setattr(files, "_open", state["opened"].append)
    monkeypatch.setattr(files, "_show_in_explorer", state["shown"].append)
    monkeypatch.setattr(files.Path, "home", lambda: HOME)
    return state


def test_finds_and_offers_to_open_the_newest_match(index):
    index["results"] = [files.FoundFile(HOME / "Documents" / "Jobs" / "Resume 2026.docx", datetime.now())]

    tts, result = _run("find my resume")

    assert index["searched"] == [["resume"]]
    assert result.question == "I found Resume 2026.docx in Documents, Jobs, changed today. Open it?"
    assert result.choices == YES_NO
    result.resume("yes")
    assert index["opened"] == [HOME / "Documents" / "Jobs" / "Resume 2026.docx"]


def test_several_matches(index):
    now = datetime.now()
    index["results"] = [files.FoundFile(HOME / "Documents" / f"budget {i}.xlsx", now - timedelta(days=i))
                        for i in range(5)]
    _, result = _run("where is my budget")
    assert result.question.startswith("I found at least 5 files. The newest is budget 0.xlsx in Documents")
    assert "Others include budget 1.xlsx, budget 2.xlsx." in result.question
    result.resume("no")
    assert index["opened"] == []


def test_nothing_found(index):
    tts, result = _run("find my tax return")
    assert result.done and "couldn't find a file called tax return" in tts.said[-1]


def test_search_unavailable(monkeypatch):
    def broken(words, home=None, limit=5):
        raise OSError("provider not found")
    monkeypatch.setattr(files, "search_index", broken)
    tts, _ = _run("find my resume")
    assert "Windows Search may be turned off" in tts.said[-1]


def test_a_found_program_is_never_opened_by_voice(index):
    index["results"] = [files.FoundFile(HOME / "Downloads" / "setup.exe", datetime.now())]
    tts, result = _run("find my setup")
    assert result.done and index["opened"] == []
    assert index["shown"] == [HOME / "Downloads" / "setup.exe"]
    assert "won't open it by voice" in tts.said[-1]


def test_the_query_is_limited_to_your_folder_and_safe_from_what_you_said():
    query = files.build_query(["o'brien%", "cv"], HOME)
    assert "SCOPE='file:C:/Users/me'" in query
    assert "LIKE '%obrien%'" in query and "LIKE '%cv%'" in query
    assert f"NOT System.ItemPathDisplay LIKE '{HOME / 'AppData'}%'" in query


@pytest.mark.parametrize("target, words", [
    ("my resume", ["resume"]), ("the file called budget 2026", ["budget", "2026"]), ("my", ["my"]),
])
def test_search_words(target, words):
    assert files.search_words(target) == words


def test_when_and_where():
    today = date(2026, 11, 23)
    assert files.when(datetime(2026, 11, 23, 9), today) == "today"
    assert files.when(datetime(2026, 11, 22, 9), today) == "yesterday"
    assert files.when(datetime(2026, 11, 3, 9), today) == "on Tuesday, November 3"
    assert files.where(HOME / "OneDrive" / "Documents" / "Jobs" / "cv.pdf", HOME) == "in Documents, Jobs"
    assert files.where(HOME / "cv.pdf", HOME) == "in your user folder"


# --- latest download ----------------------------------------------------------------------

def _download(folder: Path, name: str, minutes_ago: int) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(b"x")
    stamp = (datetime.now() - timedelta(minutes=minutes_ago)).timestamp()
    os.utime(path, (stamp, stamp))
    return path


def test_latest_download_asks_then_opens(index, monkeypatch, tmp_path):
    monkeypatch.setattr(files, "_downloads_dir", lambda: tmp_path)
    _download(tmp_path, "old.pdf", 60)
    newest = _download(tmp_path, "ticket.pdf", 5)
    _download(tmp_path, "movie.mp4.crdownload", 1)  # still downloading: skipped

    _, result = _run("open my latest download")

    assert result.question == "Your latest download is ticket.pdf, downloaded today. Open it?"
    result.resume("yes")
    assert index["opened"] == [newest]


def test_a_downloaded_program_is_shown_not_opened(index, monkeypatch, tmp_path):
    monkeypatch.setattr(files, "_downloads_dir", lambda: tmp_path)
    installer = _download(tmp_path, "free-game.exe", 1)
    tts, result = _run("open the last file i downloaded")
    assert result.done and index["opened"] == [] and index["shown"] == [installer]


def test_empty_downloads(index, monkeypatch, tmp_path):
    monkeypatch.setattr(files, "_downloads_dir", lambda: tmp_path)
    tts, _ = _run("open my latest download")
    assert tts.said == ["Your Downloads folder is empty."]


def test_the_real_index_is_never_used_in_tests():
    with pytest.raises(RuntimeError, match="Windows Search"):
        files.search_index(["x"])
