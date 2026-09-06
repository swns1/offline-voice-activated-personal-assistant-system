"""Named multi-step routines defined in config/registry.yaml's
"routines:" section (e.g. "good morning": [{intent: ..., target: ...},
...]), triggered by "run my X routine" / "start the X routine".

Resolution only lives here -- finding which routine and its steps.
Execution reuses ash/actions/chain.py's run_chain() directly from
dispatch(), since this module can't import dispatcher.py's _HANDLERS
without a circular import.
"""
from rapidfuzz import fuzz, process, utils

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
