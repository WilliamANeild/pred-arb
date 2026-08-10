"""Matcher ABC. A matcher consumes market references and emits MarketGroups."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..common.types import MarketGroup, MarketRef


class Matcher(ABC):
    name: str = "base"

    @abstractmethod
    def build(self, refs: list[MarketRef]) -> list[MarketGroup]:
        """Group the given markets. Groups with < 2 members are dropped upstream."""
