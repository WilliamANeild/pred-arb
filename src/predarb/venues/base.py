"""VenueAdapter: the uniform interface every prediction market plugs into.

Reads return normalized `Snapshot`s (probability units, YES side). Writes are
optional and gated — a read-only venue simply reports supports_trading() == False.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..common.types import Leg, MarketRef, Snapshot


class VenueAdapter(ABC):
    name: str = "base"
    env: str = "demo"           # "demo" | "prod" — real money only ever flows in "prod"
    market_type: str = "orderbook"   # "orderbook" (depth, tradeable) | "fixed_odds" (quote-only)
    executable: bool = False    # can we place orders here via API at all?

    @abstractmethod
    def list_markets(self, **filt) -> list[MarketRef]:
        """Discover markets (optionally filtered). Used by matchers/recorder."""

    @abstractmethod
    def get_snapshot(self, ref: MarketRef) -> Snapshot:
        """Current normalized book for one market."""

    def supports_trading(self) -> bool:
        """True only if this venue is BOTH executable and currently authenticated."""
        return self.executable

    @property
    def quote_only(self) -> bool:
        """A venue we can read for consensus but never route an order to."""
        return self.market_type == "fixed_odds" or not self.executable

    def place(self, leg: Leg, *, client_order_id: str | None = None) -> dict:
        raise NotImplementedError(f"{self.name} does not support trading")
