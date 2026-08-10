"""Live executor — places REAL orders. Hard-gated; not reachable by default.

Every order passes BOTH SafetyGate.check() and SafetyGate.live_guard(), plus an
interactive confirmation. If any venue leg can't trade (e.g. Polymarket is
read-only in the POC) the whole opportunity is rejected — we never place a
one-legged version of a two-legged lock.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..common.logenv import get_logger
from ..common.types import Opportunity, Snapshot
from ..venues.base import VenueAdapter
from .safety import SafetyGate

log = get_logger("execute.live")

CONFIRM_PHRASE = "TRADE REAL MONEY"


@dataclass
class LiveReport:
    placed: list[dict] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)


class LiveExecutor:
    def __init__(self, gate: SafetyGate, adapters: dict[str, VenueAdapter],
                 *, run_live_flag: bool, confirm=input):
        self.gate = gate
        self.adapters = adapters
        self.run_live_flag = run_live_flag
        self.confirm = confirm            # injectable for tests
        self.report = LiveReport()

    def _all_legs_tradeable(self, opp: Opportunity) -> str | None:
        for leg in opp.legs:
            a = self.adapters.get(leg.venue)
            if a is None:
                return f"no adapter for {leg.venue}"
            if not a.supports_trading():
                return f"{leg.venue} is not trading-enabled (read-only)"
            if a.env != "prod":
                return f"{leg.venue} env is {a.env}, not prod"
        return None

    def execute(self, opp: Opportunity, qty: int, snaps: dict[str, Snapshot]) -> bool:
        snap_ts = min((snaps[f"{leg.venue}:{leg.market_id}"].ts for leg in opp.legs
                       if f"{leg.venue}:{leg.market_id}" in snaps), default=None)
        # 1. standard caps/breakers
        reason = self.gate.check(opp, qty, snap_ts=snap_ts)
        if reason:
            self.report.blocked.append(f"{opp.group_key}: {reason}")
            return False
        # 2. real-money-only gate (riskless-only, edge floor, prod env, --live, ...)
        venue_env = next((self.adapters[l.venue].env for l in opp.legs
                          if l.venue in self.adapters), "demo")
        reason = self.gate.live_guard(opp, venue_env, self.run_live_flag)
        if reason:
            self.report.blocked.append(f"{opp.group_key}: {reason}")
            return False
        # 3. every leg must be really tradeable
        reason = self._all_legs_tradeable(opp)
        if reason:
            self.report.blocked.append(f"{opp.group_key}: {reason}")
            return False
        # 4. interactive confirmation
        prompt = (f"\nPLACE REAL ORDER  {opp.group_key}  {opp.kind}  x{qty}  "
                  f"edge={opp.edge:.3f}\nType '{CONFIRM_PHRASE}' to proceed: ")
        if self.confirm(prompt).strip() != CONFIRM_PHRASE:
            self.report.blocked.append(f"{opp.group_key}: confirmation declined")
            return False

        # place each leg
        for leg in opp.legs:
            try:
                res = self.adapters[leg.venue].place(leg)
                self.report.placed.append({"group": opp.group_key, "leg": leg.market_id, "res": res})
            except Exception as e:  # noqa: BLE001
                self.gate.note_error()
                self.report.blocked.append(f"{opp.group_key}: place failed on {leg.market_id}: {e}")
                return False
        self.gate.record_fill(opp, qty)
        log.warning("LIVE placed %s x%d", opp.group_key, qty)
        return True
