"""Paper broker — simulates fills against the live book and tracks positions.

This is the DEFAULT execution path. It runs the exact same SafetyGate the live
executor does, so paper and live behave identically except that paper never
touches a venue. Use it to build a track record before risking a cent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..backtest.fills import simulate_fill
from ..common.config import load_params
from ..common.logenv import get_logger
from ..common.types import Opportunity, Snapshot
from .safety import GateState, SafetyGate

log = get_logger("execute.paper")


@dataclass
class PaperOrder:
    group_key: str
    market_id: str
    side: str
    qty: int
    price: float
    cost_usd: float


@dataclass
class PaperReport:
    filled: list[PaperOrder] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)

    @property
    def deployed_usd(self) -> float:
        return sum(o.cost_usd for o in self.filled)


class PaperBroker:
    def __init__(self, gate: SafetyGate, params: dict | None = None):
        self.gate = gate
        self.params = params or load_params()
        self.report = PaperReport()

    def execute(self, opp: Opportunity, qty: int, snaps: dict[str, Snapshot]) -> bool:
        """Attempt to paper-fill every leg at `qty`. Returns True on full fill."""
        snap_ts = min((snaps[f"{leg.venue}:{leg.market_id}"].ts for leg in opp.legs
                       if f"{leg.venue}:{leg.market_id}" in snaps), default=None)
        reason = self.gate.check(opp, qty, snap_ts=snap_ts)
        if reason:
            self.report.blocked.append(f"{opp.group_key}: {reason}")
            return False

        fills = []
        for leg in opp.legs:
            snap = snaps.get(f"{leg.venue}:{leg.market_id}")
            if snap is None:
                self.report.blocked.append(f"{opp.group_key}: no snapshot for {leg.market_id}")
                return False
            levels = (snap.book.yes_ask_levels if leg.side == "yes"
                      else snap.book.no_ask_levels())
            fill = simulate_fill(levels, qty, venue=leg.venue,
                                 haircut=self.params["phantom_haircut"],
                                 fee_rate=self.params["kalshi_fee_rate"])
            if fill.filled < qty:
                self.report.blocked.append(
                    f"{opp.group_key}: partial fill {fill.filled}/{qty} on {leg.market_id}")
                return False
            fills.append((leg, fill))

        for leg, fill in fills:
            self.report.filled.append(PaperOrder(
                group_key=opp.group_key, market_id=leg.market_id, side=leg.side,
                qty=fill.filled, price=fill.avg_price, cost_usd=fill.cost_usd,
            ))
        self.gate.record_fill(opp, qty)
        log.info("PAPER filled %s x%d (%s, edge=%.3f, conf=%.2f)",
                 opp.group_key, qty, opp.kind, opp.edge, opp.confidence)
        return True


def new_paper_broker(safety, params=None) -> PaperBroker:
    return PaperBroker(SafetyGate(safety, GateState()), params)
