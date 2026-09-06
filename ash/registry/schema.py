"""Pydantic models mirroring registry.yaml. The `launch` block is kept as
a loosely-typed dict rather than a discriminated union: launchers each
read only the keys they care about via `.get`/`[...]`, so new launch
types (new launcher-gated ecosystems) are additive data, not schema
changes.
"""
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AppEntry(BaseModel):
    id: str
    names: list[str]
    launch: dict[str, Any]
    source: str = "manual"

    @field_validator("launch")
    @classmethod
    def _launch_has_type(cls, v: dict[str, Any]) -> dict[str, Any]:
        if "type" not in v:
            raise ValueError("launch block must include a 'type' key")
        return v


class IntentConfig(BaseModel):
    verbs: list[str]
    launch: dict[str, Any]


class Registry(BaseModel):
    apps: list[AppEntry] = Field(default_factory=list)
    intents: dict[str, IntentConfig] = Field(default_factory=dict)
    # routine name -> ordered list of {"intent": ..., "target": ...} steps,
    # run in sequence by ash/actions/routines.py. Loosely typed like
    # AppEntry.launch, for the same reason -- a step is just whatever its
    # intent's handler already expects.
    routines: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
