"""When the rule-based grammar (ash/nlu/grammar.py) doesn't recognize
any verb phrase in an utterance, it defaults to treating the whole
thing as "open <utterance>" -- the most permissive interpretation, but
wrong for natural phrasing that doesn't match a literal template ("dim
the volume a bit", "shut this thing down"). Before that guess is acted
on, ash/actions/dispatcher.py asks the local Ollama model (only if
ash.utils.ollama.ai_enabled) which of Ash's commands it means, offering
them as tools (Ollama's native tool calling, see ash/nlu/tools.py); if
it confidently picks one, that replaces the "open" guess. If Ollama is
disabled, unreachable, times out, or isn't confident, the existing "open" -> app-match -> converse fallback chain
(see ash/actions/open_app.py) proceeds completely unchanged -- this is
purely additive.

Deliberately a separate, smaller intent list from
ash/actions/chain.py's _CHAINABLE_INTENTS: this classifies one single
command, not a multi-step sequence, so confirm-gated intents (shutdown)
are safe to include here -- whatever intent comes back still passes
through dispatcher.py's normal needs_confirmation()/
wrap_with_confirmation() before its handler runs, same as if the user
had said the literal template phrase.
"""
from ash.config import Config
from ash.nlu.intents import ParsedCommand
from ash.nlu.tools import plan
from ash.skills import registry as skills

# Sits in front of every unmatched command (when the local AI is on),
# so a slow or hung model falls back to the existing "open" guess rather
# than stall. Longer than a plain classification needed, since the
# model now reads each command's description: the first request after
# the model loads is the slow one (Ollama reuses the unchanged prefix).
_TIMEOUT_SECONDS = 20.0

_SYSTEM = (
    "You are the command understanding of a voice assistant. Its rule-based parser didn't recognise "
    "what the user said. If it clearly means one of the available tools, call that one tool. If it's a "
    "question, small talk, a request to open or play something, or doesn't clearly match a tool, call "
    "no tool and reply with an empty message."
)


def classify_intent(text: str, config: Config) -> ParsedCommand | None:
    """The one command the local AI is confident `text` means, or None
    (no match, more than one, unreachable, or anything unexpected) --
    callers then keep the grammar's original "open" guess."""
    try:
        commands = plan(text, config, skills.classifiable_intents(), _SYSTEM, _TIMEOUT_SECONDS)
    except Exception:
        return None
    if not commands or len(commands) != 1:
        return None
    return commands[0]
