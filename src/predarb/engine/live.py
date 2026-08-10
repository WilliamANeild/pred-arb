"""Live engine — the continuous loop: snapshot every venue, build consensus across
ALL of them (including read-only sportsbook lines), and route tradeable
opportunities through the leg-risk executor.

Quote-only venues (fixed-odds sportsbooks) contribute to consensus but are never
routed an order — enforced both by empty ladders in the signal layer and by the
executor's `executable_venues` guard here. Paper backend by default; the live
backend stays fenced off until fill-confirmation is built.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..common.config import SafetyConfig, load_params
from ..common.logenv import get_logger
from ..common.types import MarketRef, Snapshot
from ..execute.backends import PaperBackend
from ..execute.legrisk import LegRiskExecutor, LegRiskReport
from ..execute.safety import GateState, SafetyGate
from ..matching import build_matcher
from ..signal.profiles import build_profile
from ..sizing.confidence import size_opportunity
from ..venues.base import VenueAdapter

log = get_logger("engine.live")


@dataclass
class SessionReport:
    cycles: int = 0
    filled: int = 0
    deployed_usd: float = 0.0
    unwound: int = 0
    blocked: list[str] = field(default_factory=list)


class LiveEngine:
    def __init__(self, adapters: dict[str, VenueAdapter], *, matcher: str, profile: str,
                 params: dict | None = None, safety: SafetyConfig | None = None,
                 backend=None, live: bool = False):
        self.adapters = adapters
        self.matcher_name = matcher
        self.profile = build_profile(profile)
        self.params = params or load_params()
        self.safety = safety or SafetyConfig()
        self.gate = SafetyGate(self.safety, GateState())
        self.backend = backend or PaperBackend(self.params)
        # paper can simulate any order-book venue; live only genuinely tradeable ones.
        if live:
            self.executable = {n for n, a in adapters.items() if a.supports_trading()}
        else:
            self.executable = {n for n, a in adapters.items() if a.market_type == "orderbook"}
        self.executor = LegRiskExecutor(self.gate, self.backend, self.params,
                                        executable_venues=self.executable)
        self.report = SessionReport()

    def discover(self, limit: int = 200) -> list[MarketRef]:
        refs: list[MarketRef] = []
        for a in self.adapters.values():
            try:
                refs += a.list_markets(limit=limit)
            except Exception as e:  # noqa: BLE001
                log.warning("%s list_markets failed: %s", a.name, e)
        return refs

    def _snapshot(self, refs: list[MarketRef], wanted: set[str]) -> dict[str, Snapshot]:
        snaps: dict[str, Snapshot] = {}
        for r in refs:
            if r.key not in wanted:
                continue
            a = self.adapters.get(r.venue)
            if a is None:
                continue
            try:
                snaps[r.key] = a.get_snapshot(r)
            except Exception:  # noqa: BLE001
                pass
        return snaps

    def run(self, *, cycles: int | None = None, minutes: float | None = None,
            interval_s: float = 10.0, limit: int = 200) -> SessionReport:
        refs = self.discover(limit)
        groups = build_matcher(self.matcher_name).build(refs)
        wanted = {m.key for g in groups for m in g.members}
        log.info("engine: %d markets, %d groups, executable venues=%s",
                 len(refs), len(groups), sorted(self.executable))

        deadline = time.time() + minutes * 60 if minutes else None
        c = 0
        while True:
            if self.safety.kill_engaged():
                log.warning("kill switch engaged — stopping")
                break
            snaps = self._snapshot(refs, wanted)
            for g in groups:
                for opp in self.profile.evaluate(g, snaps, self.params, self.safety):
                    qty = size_opportunity(opp, self.safety, self.params)
                    if qty <= 0:
                        continue
                    rep = self._route(opp, qty, snaps)
                    if rep.success:
                        self.report.filled += 1
                        self.report.deployed_usd += rep.realized_cost_usd
                    elif rep.unwound:
                        self.report.unwound += 1
                        self.report.blocked.append(f"{opp.group_key}: {rep.note}")
                    else:
                        self.report.blocked.append(f"{opp.group_key}: {rep.note}")
            c += 1
            self.report.cycles = c
            if cycles and c >= cycles:
                break
            if deadline and time.time() >= deadline:
                break
            time.sleep(interval_s)
        return self.report

    def _route(self, opp, qty, snaps) -> LegRiskReport:
        return self.executor.execute(opp, qty, snaps)
