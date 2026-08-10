"""The record a backtest emits per closed position."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BacktestTrade:
    group_key: str
    matcher: str
    profile: str
    kind: str                  # "dutch_book" | "relative_value"
    qty: int
    cost_usd: float            # capital put at risk to enter
    payoff_usd: float          # returned at exit/settlement
    entry_ts: float
    exit_ts: float
    exit_kind: str             # "settle" | "converge" | "mark"
    edge_expected: float
    legs: list = field(default_factory=list)

    @property
    def pnl_usd(self) -> float:
        return self.payoff_usd - self.cost_usd
