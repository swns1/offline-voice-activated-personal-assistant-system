"""Email through your desktop Outlook, over COM (the same way as the
calendar, ash/actions/calendar.py). Off unless email.enabled is on.

- "check my email": how many are unread, then the sender and subject of
  the latest few. Never the message itself: bodies can be long, private
  and full of links, and are read aloud in a room.
- "email Anna saying I'm running late": looks Anna up in Outlook's
  address book, then asks first, saying exactly who it goes to (name
  and address), the subject, and the whole message. Only a clear yes
  sends it; with voice-verified confirmation on, it must also be your
  voice.

Nothing is stored, and neither addresses nor message text reach the
log. Outlook itself sends the email, over your mail account; that's
outside Ash's network gate, and disclosed as such in docs/PRIVACY.md.
"""
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from ash.actions.confirmation import ask_to_confirm
from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.nlu.context import original_case
from ash.registry.schema import Registry

_OL_FOLDER_INBOX = 6
_OL_MAIL_ITEM = 0
_LATEST = 3
_SUBJECT_WORDS = 8

NOT_SET_UP = "Email isn't set up. Turn it on in Settings, under Answers, if you use Outlook."
UNREACHABLE = "I can't reach Outlook right now."


@dataclass(frozen=True)
class Recipient:
    name: str
    address: str


@dataclass(frozen=True)
class Message:
    sender: str
    subject: str


@contextmanager
def _outlook() -> Iterator:
    """Outlook's MAPI namespace. Raises if Outlook isn't installed or set up."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        yield win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
    finally:
        pythoncom.CoUninitialize()


def unread_and_latest(count: int = _LATEST) -> tuple[int, list[Message]]:
    with _outlook() as namespace:
        inbox = namespace.GetDefaultFolder(_OL_FOLDER_INBOX)
        items = inbox.Items
        items.Sort("[ReceivedTime]", True)
        latest = []
        for item in items:
            if len(latest) >= count:
                break
            try:
                latest.append(Message(sender=str(item.SenderName), subject=str(item.Subject)))
            except Exception:
                continue  # meeting requests and the like have no sender
        return int(inbox.UnReadItemCount), latest


def resolve(name: str) -> Recipient | None:
    """One address-book match for `name`, or None (no match, or more than
    one: Outlook won't resolve an ambiguous name, and neither will Ash)."""
    with _outlook() as namespace:
        recipient = namespace.CreateRecipient(name)
        if not recipient.Resolve():
            return None
        entry = recipient.AddressEntry
        address = str(entry.Address)
        try:
            exchange_user = entry.GetExchangeUser()
            if exchange_user is not None:
                address = str(exchange_user.PrimarySmtpAddress)
        except Exception:
            pass
        return Recipient(name=str(recipient.Name), address=address)


def send(recipient: Recipient, subject: str, body: str) -> None:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        mail = win32com.client.Dispatch("Outlook.Application").CreateItem(_OL_MAIL_ITEM)
        mail.To = recipient.address
        mail.Subject = subject
        mail.Body = body
        mail.Send()
    finally:
        pythoncom.CoUninitialize()


# --- reading ------------------------------------------------------------------------

def handle_email_check(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger,
                       config: Config) -> HandlerResult:
    if not config.email.enabled:
        tts.say(NOT_SET_UP)
        return HandlerResult()
    try:
        unread, latest = unread_and_latest()
    except Exception:
        log.warning("Could not read the Outlook inbox", exc_info=True)
        tts.say(UNREACHABLE)
        return HandlerResult()
    log.info("Read the inbox summary (%d unread)", unread)
    if not latest:
        tts.say("Your inbox is empty.")
        return HandlerResult()
    count = "no unread emails" if unread == 0 else f"{unread} unread email{'' if unread == 1 else 's'}"
    listed = "; ".join(f"from {m.sender}: {m.subject or 'no subject'}" for m in latest)
    tts.say(f"You have {count}. The latest: {listed}.")
    return HandlerResult()


# --- sending ------------------------------------------------------------------------

_SPLIT = re.compile(r"^(?P<who>.+?)\s+(?:saying|that says|to say|and say|and tell (?:him|her|them))\s+(?P<body>.+)$")


def parse_send(target: str) -> tuple[str, str]:
    """"Anna saying I'm running late" -> ("Anna", "I'm running late").
    The message may be empty ("email Anna"): Ash then asks for it."""
    target = re.sub(r"^(?:to|an email to|a message to)\s+", "", target.strip())
    match = _SPLIT.match(target)
    if match is None:
        return target, ""
    return match["who"].strip(), match["body"].strip()


def _spoken_address(name: str) -> str:
    """"anna at example dot com" (an address said out loud, as
    speech-to-text writes it) -> "anna@example.com". Names pass through."""
    if "@" in name:
        return name.replace(" ", "")
    if " at " in f" {name} " and " dot " in f" {name} ":
        return re.sub(r"\s+dot\s+", ".", re.sub(r"\s+at\s+", "@", name.strip())).replace(" ", "")
    return name


def subject_for(body: str) -> str:
    words = body.rstrip(".!?").split()
    subject = " ".join(words[:_SUBJECT_WORDS]) + ("…" if len(words) > _SUBJECT_WORDS else "")
    return subject[:1].upper() + subject[1:]


def handle_email_send(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger,
                      config: Config) -> HandlerResult:
    if not config.email.enabled:
        tts.say(NOT_SET_UP)
        return HandlerResult()
    who, body = parse_send(target)
    body = original_case(body)  # the grammar lowercased it; an email shouldn't be
    if not who:
        tts.say("Who should I email? Say, for example, 'email Anna saying I'm running late'.")
        return HandlerResult()
    if not body:
        return HandlerResult(
            done=False, question=f"What should the email to {who} say?",
            resume=lambda answer: _confirm(who, answer.strip(), tts, log, config),
        )
    return _confirm(who, body, tts, log, config)


def _confirm(who: str, body: str, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    if not body:
        tts.say("Okay, no email.")
        return HandlerResult()
    if body[-1] not in ".!?":
        body += "."
    address = _spoken_address(who)
    try:
        recipient = Recipient(name=address, address=address) if "@" in address else resolve(who)
    except Exception:
        log.warning("Could not reach the Outlook address book", exc_info=True)
        tts.say(UNREACHABLE)
        return HandlerResult()
    if recipient is None:
        tts.say(f"I couldn't find exactly one contact called {who} in Outlook, so I haven't sent anything.")
        return HandlerResult()

    subject = subject_for(body)
    to = recipient.address if recipient.name == recipient.address else f"{recipient.name}, {recipient.address}"

    def send_it() -> HandlerResult:
        try:
            send(recipient, subject, body)
        except Exception:
            log.warning("Outlook could not send the email", exc_info=True)
            tts.say("Outlook couldn't send that email. Nothing was sent.")
            return HandlerResult()
        log.info("Sent an email through Outlook")
        tts.say(f"Sent to {recipient.name}.")
        return HandlerResult()

    return ask_to_confirm(
        f"I'll email {to}, with the subject '{subject}', saying: '{body}' Send it?",
        send_it, action="email_send", declined_reply="Okay, I haven't sent it.",
        tts=tts, log=log, config=config,
    )
