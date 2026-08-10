"""Core data types shared across venues, matching, signal, and backtest.

Everything is normalized to PROBABILITY units (0..1) on the YES side so that a
Kalshi market priced in cents and a Polymarket market priced in USDC are directly
comparable. A price of 0.42 means "buy YES for $0.42, settles $1.00 or $0.00".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

Side = Literal["yes", "no"]


@dataclass(frozen=True)
class MarketRef:
    """Identity of a single tradeable market on a venue."""
    venue: str
    market_id: str
    title: str = ""
    event_id: str = ""          # groups mutually-exclusive outcomes (intra-event matcher)
    yes_meaning: str = ""       # human description of what a YES resolution means

    @property
    def key(self) -> str:
        return f"{self.venue}:{self.market_id}"


@dataclass
class Book:
    """Top-of-book + ladders in PROBABILITY units on the YES side.

    yes_ask = cheapest probability you can BUY yes at (what you pay).
    yes_bid = best probability you can SELL yes at (what you receive).
    Levels are (price_prob, qty_contracts), asks ascending, bids descending.
    """
    yes_bid: Optional[float] = None
    yes_ask: Optional[float] = None
    yes_ask_levels: list[tuple[float, int]] = field(default_factory=list)
    yes_bid_levels: list[tuple[float, int]] = field(default_factory=list)

    @property
    def mid(self) -> Optional[float]:
        if self.yes_bid is not None and self.yes_ask is not None:
            return 0.5 * (self.yes_bid + self.yes_ask)
        return self.yes_bid if self.yes_bid is not None else self.yes_ask

    @property
    def spread(self) -> Optional[float]:
        if self.yes_bid is None or self.yes_ask is None:
            return None
        return self.yes_ask - self.yes_bid

    @property
    def yes_ask_qty(self) -> int:
        return self.yes_ask_levels[0][1] if self.yes_ask_levels else 0

    @property
    def yes_bid_qty(self) -> int:
        return self.yes_bid_levels[0][1] if self.yes_bid_levels else 0

    def no_ask_levels(self) -> list[tuple[float, int]]:
        """Buying NO at prob q is selling YES at (1-q): the NO ask ladder is the
        YES bid ladder reflected. Ascending by NO price."""
        return sorted(((1.0 - p, q) for p, q in self.yes_bid_levels), key=lambda x: x[0])

    @property
    def no_ask(self) -> Optional[float]:
        """Cheapest probability you can BUY no at = 1 - best yes bid."""
        return None if self.yes_bid is None else 1.0 - self.yes_bid


@dataclass
class Snapshot:
    """A market's book at a point in time. `settle` is set only for resolved
    markets (1.0 = YES won, 0.0 = NO won); None while open."""
    ref: MarketRef
    book: Book
    ts: float
    settle: Optional[float] = None


@dataclass(frozen=True)
class GroupMember:
    venue: str
    market_id: str
    polarity: int = 1   # +1: member-YES == event-YES ; -1: member-YES == event-NO

    @property
    def key(self) -> str:
        return f"{self.venue}:{self.market_id}"


@dataclass
class MarketGroup:
    """A set of markets asserted to resolve on the same underlying event."""
    key: str
    members: list[GroupMember]
    kind: str = "equivalence"      # "equivalence" | "partition"
    trust: float = 1.0             # matcher confidence in the grouping (0..1)
    matcher: str = ""              # which matcher produced this group
    note: str = ""


@dataclass
class Leg:
    """One order within an opportunity, in normalized YES-probability terms.
    side="yes" buys YES at `price`; side="no" buys NO at `price` (= sell YES)."""
    venue: str
    market_id: str
    side: Side
    price: float        # probability paid at entry
    qty: int

    @property
    def notional(self) -> float:
        return self.price * self.qty


@dataclass
class Opportunity:
    """A tradeable signal produced by a risk profile from a group."""
    group_key: str
    kind: str                       # "dutch_book" | "relative_value"
    legs: list[Leg]
    edge: float                     # fee-adjusted expected profit per $1 at risk
    consensus: float                # p*(event=yes)
    dispersion: float
    p_win: float = 1.0              # prob this position pays $1 (1.0 for a lock)
    confidence: float = 0.0         # 0..1, set by sizing
    trust: float = 1.0
    matcher: str = ""
    note: str = ""

    @property
    def cost(self) -> float:
        return sum(leg.notional for leg in self.legs)
