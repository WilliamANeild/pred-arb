"""Leg-risk executor — the safeguard that makes MULTI-LEG, cross-venue arbitrage
safe to attempt live.

A cross-venue lock is never atomic: you fill one leg on Kalshi, another on
Polymarket, and if the second leg moves or fails before it fills, your "riskless"
lock becomes a naked directional bet. This executor bounds that risk:

  1. Route only to EXECUTABLE venues (never a fixed-odds sportsbook quote).
  2. Fill the hardest leg first (thinnest book) so a failure happens before we've
     committed the easy leg.
  3. Abort if any leg fills worse than `max_leg_drift` vs its quote.
  4. On any failure, UNWIND every already-filled leg immediately (accept a small,
     bounded loss) rather than hold an unbalanced position.

It is backend-agnostic: the same logic runs against the paper backend (simulated
fills) and the live backend (real orders), so paper is a faithful dry run.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..common.logenv import get_logger
from ..common.types import Leg, Opportunity, Snapshot
from .safety import SafetyGate

log = get_logger("execute.legrisk")


@dataclass
class LegFill:
    leg: Leg
    filled: int
    avg_price: float
    cost_usd: float


class ExecutionBackend(ABC):
    """How legs actually get filled/unwound. Paper simulates; live places orders."""
    name = "base"

    @abstractmethod
    def place(self, leg: Leg, qty: int, snaps: dict[str, Snapshot]) -> LegFill: ...

    @abstractmethod
    def unwind(self, fill: LegFill, snaps: dict[str, Snapshot]) -> float:
        """Reverse a filled leg. Returns proceeds recovered (USD)."""


@dataclass
class LegRiskReport:
    success: bool
    fills: list[LegFill] = field(default_factory=list)
    unwound: list[LegFill] = field(default_factory=list)
    realized_cost_usd: float = 0.0     # net cost including any unwind slippage
    note: str = ""


def _depth_of(leg: Leg, snaps: dict[str, Snapshot]) -> int:
    snap = snaps.get(f"{leg.venue}:{leg.market_id}")
    if snap is None:
        return 0
    levels = snap.book.yes_ask_levels if leg.side == "yes" else snap.book.no_ask_levels()
    return sum(q for _, q in levels)


class LegRiskExecutor:
    def __init__(self, gate: SafetyGate, backend: ExecutionBackend, params: dict,
                 *, executable_venues: set[str] | None = None):
        self.gate = gate
        self.backend = backend
        self.params = params
        self.executable_venues = executable_venues  # None = trust the opp's legs

    def _ordered_legs(self, opp: Opportunity, snaps: dict[str, Snapshot]) -> list[Leg]:
        if self.params.get("leg_order") == "thin_first":
            return sorted(opp.legs, key=lambda l: _depth_of(l, snaps))
        return list(opp.legs)

    def execute(self, opp: Opportunity, qty: int, snaps: dict[str, Snapshot]) -> LegRiskReport:
        snap_ts = min((snaps[f"{l.venue}:{l.market_id}"].ts for l in opp.legs
                       if f"{l.venue}:{l.market_id}" in snaps), default=None)
        reason = self.gate.check(opp, qty, snap_ts=snap_ts)
        if reason:
            return LegRiskReport(success=False, note=reason)

        # never route to a non-executable / fixed-odds venue
        if self.executable_venues is not None:
            bad = [l.venue for l in opp.legs if l.venue not in self.executable_venues]
            if bad:
                return LegRiskReport(success=False, note=f"non-executable leg venue(s): {sorted(set(bad))}")

        max_drift = self.params["max_leg_drift"]
        fills: list[LegFill] = []
        for leg in self._ordered_legs(opp, snaps):
            fill = self.backend.place(leg, qty, snaps)
            # failure 1: couldn't get the full size
            if fill.filled < qty:
                return self._unwind_all(fills, snaps, f"partial fill {fill.filled}/{qty} on {leg.market_id}")
            # failure 2: filled materially worse than quoted
            if fill.avg_price - leg.price > max_drift:
                self.backend.unwind(fill, snaps)   # unwind the leg we just overpaid on too
                return self._unwind_all(fills, snaps,
                                        f"leg drift {fill.avg_price - leg.price:.3f} > {max_drift} on {leg.market_id}")
            fills.append(fill)

        self.gate.record_fill(opp, qty)
        cost = sum(f.cost_usd for f in fills)
        log.info("LEG-LOCK filled %s x%d cost $%.2f (%s)", opp.group_key, qty, cost, self.backend.name)
        return LegRiskReport(success=True, fills=fills, realized_cost_usd=cost, note="filled")

    def _unwind_all(self, fills: list[LegFill], snaps, note: str) -> LegRiskReport:
        if not self.params.get("unwind_on_fail", True):
            return LegRiskReport(success=False, fills=fills, note=f"{note} (unwind disabled — legs left open!)")
        recovered = 0.0
        for f in fills:
            recovered += self.backend.unwind(f, snaps)
        spent = sum(f.cost_usd for f in fills)
        log.warning("UNWOUND %d leg(s): %s | net loss $%.2f", len(fills), note, spent - recovered)
        return LegRiskReport(success=False, fills=[], unwound=fills,
                             realized_cost_usd=spent - recovered, note=f"unwound: {note}")
