"""Common interface every launcher implementation follows."""
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any


class Launcher(ABC):
    @abstractmethod
    def can_handle(self, launch: Mapping[str, Any]) -> bool:
        """Whether this launcher knows how to execute a registry entry's `launch` block."""

    @abstractmethod
    def launch(self, launch: Mapping[str, Any]) -> None:
        """Execute the entry. Raises on failure; callers decide what to say/log."""
