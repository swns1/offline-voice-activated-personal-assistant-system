"""Named multi-step routines defined in config/registry.yaml's
"routines:" section (e.g. "good morning": [{intent: ..., target: ...},
...]), triggered by "run my X routine" / "start the X routine".

Resolution only lives here -- finding which routine and its steps.
Execution reuses ash/actions/chain.py's run_chain() directly from
dispatch(), since this module can't import dispatcher.py's _HANDLERS
without a circular import.
"""
import logging

from rapidfuzz import fuzz, process, utils

from ash.actions.chain import run_chain
from ash.actions.results import HandlerResult
from ash.audio.tts import TtsWorker
from ash.config import Config
from ash.privacy.redact import said
from ash.registry.schema import Registry

_FUZZY_SCORE_CUTOFF = 80.0


def resolve_routine_name(target: str) -> str:
    name = target.strip().lower()
    if name.endswith(" routine"):
        name = name[: -len(" routine")].strip()
    return name


def find_routine(name: str, registry: Registry) -> list[dict] | None:
    if not name:
        return None
    if name in registry.routines:
        return registry.routines[name]
    if not registry.routines:
        return None

    best = process.extractOne(
        name, registry.routines.keys(), scorer=fuzz.WRatio,
        processor=utils.default_process, score_cutoff=_FUZZY_SCORE_CUTOFF,
    )
    if best is None:
        return None
    matched_name, _score, _ = best
    return registry.routines[matched_name]


def handle_routine_run(target: str, registry: Registry, tts: TtsWorker, log: logging.Logger, config: Config) -> HandlerResult:
    name = resolve_routine_name(target)
    steps = find_routine(name, registry)
    if steps is None:
        log.info("No routine matches %s", said(name))
        tts.say(f"I don't have a routine called {name}.")
        return HandlerResult()
    log.info("Running routine %s (%d steps)", said(name), len(steps))
    # The dispatcher's handler table, looked up at call time: routine
    # steps run exactly like the same commands spoken one by one
    # (including any confirmation they need -- see run_chain).
    from ash.actions import dispatcher
    return run_chain(steps, dispatcher._HANDLERS, registry, tts, log, config)
