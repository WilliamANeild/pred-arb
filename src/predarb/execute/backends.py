"""Execution backends for the leg-risk executor.

PaperBackend  — simulates fills against the current book (the default, fully tested).
LiveBackend   — real orders. Intentionally refuses until fill-confirmation is wired:
                cross-venue leg-risk logic is only safe if we KNOW whether each leg
                actually filled, and confirming real fills (Kalshi resting orders,
                Polymarket on-chain settlement) is a deliberate later step. Refusing
                here is safer than optimistically assuming a fill.
"""
from __future__ import annotations

from ..backtest.fills import simulate_fill
from ..common.types import Leg, Snapshot
from ..signal.fees import kalshi_fee_usd
from .legrisk import ExecutionBackend, LegFill


class PaperBackend(ExecutionBackend):
    name = "paper"

    def __init__(self, params: dict):
        self.params = params

    def place(self, leg: Leg, qty: int, snaps: dict[str, Snapshot]) -> LegFill:
        snap = snaps.get(f"{leg.venue}:{leg.market_id}")
        if snap is None:
            return LegFill(leg, 0, 0.0, 0.0)
        levels = snap.book.yes_ask_levels if leg.side == "yes" else snap.book.no_ask_levels()
        fill = simulate_fill(levels, qty, venue=leg.venue,
                             haircut=self.params["phantom_haircut"],
                             fee_rate=self.params["kalshi_fee_rate"])
        return LegFill(leg, fill.filled, fill.avg_price, fill.cost_usd)

    def unwind(self, fill: LegFill, snaps: dict[str, Snapshot]) -> float:
        leg = fill.leg
        snap = snaps.get(f"{leg.venue}:{leg.market_id}")
        if snap is None or fill.filled == 0:
            return 0.0
        if leg.side == "yes":
            price = snap.book.yes_bid or 0.0
        else:  # we hold NO; sell it at NO-bid = 1 - yes_ask
            price = 1.0 - (snap.book.yes_ask if snap.book.yes_ask is not None else 1.0)
        fee = kalshi_fee_usd(price, fill.filled, self.params["kalshi_fee_rate"]) if leg.venue == "kalshi" else 0.0
        return max(0.0, fill.filled * price - fee)


class LiveBackend(ExecutionBackend):
    name = "live"

    def __init__(self, adapters: dict):
        self.adapters = adapters

    def place(self, leg: Leg, qty: int, snaps: dict[str, Snapshot]) -> LegFill:
        raise NotImplementedError(
            "LiveBackend is not enabled: cross-venue leg-risk execution needs real "
            "fill confirmation (Kalshi resting-order polling / Polymarket settlement) "
            "which is a deliberate later step. Keep paper until then.")

    def unwind(self, fill: LegFill, snaps: dict[str, Snapshot]) -> float:
        raise NotImplementedError("LiveBackend disabled — see place()")
