"""What Ash's log files are allowed to contain.

Logs exist for troubleshooting ("did it hear me? which command ran?"),
not to keep a record of everything you say. So by default anything you
said, searched for, or asked Ash to act on is replaced in log messages
by a placeholder such as "<4 words hidden>": the log still shows that a
command arrived and what Ash did with it, without the content. Set
`privacy.log_transcripts: true` in config.yaml to include the content,
e.g. while debugging recognition problems.

Some content is never logged, whatever that setting says: text Ash
types for you and facts you ask it to remember. Call sites simply don't
pass those to the logger at all.

In line with RA 10173 Sec. 11 (proportionality: collect only what the
purpose needs).
"""

_log_content = False


def set_log_content(enabled: bool) -> None:
    """Applied once at startup from config.privacy.log_transcripts."""
    global _log_content
    _log_content = enabled


def said(text: object) -> str:
    """Wrap anything the user said/asked for before putting it in a log
    message: returns repr(text) if content logging is on, otherwise a
    placeholder giving only its length."""
    if _log_content:
        return repr(text)
    words = len(str(text).split())
    return f"<{words} word{'' if words == 1 else 's'} hidden>"
