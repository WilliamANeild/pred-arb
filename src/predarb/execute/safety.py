"""SafetyGate — the single choke point every order passes through.

Enforces the caps, circuit breakers, and strategy guards from SafetyConfig. Both
the paper broker and the live executor call `check()` before placing anything;
there is no path to an order that skips this.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..common.config import SafetyConfig
from ..common.logenv import get_logger
from ..common.types import Opportunity

log = get_logger("execute.safety")


@dataclass
class GateState:
    realized_loss: float = 0.0
    total_notional: float = 0.0
    orders_placed: int = 0
    consecutive_errors: int = 0
    market_notional: dict[str, float] = field(default_factory=dict)
    group_notional: dict[str, float] = field(default_factory=dict)


class SafetyGate:
    def __init__(self, safety: SafetyConfig, state: GateState | None = None):
        self.safety = safety
        self.state = state or GateState()

    def check(self, opp: Opportunity, qty: int, *, snap_ts: float | None = None,
              now: float | None = None) -> str | None:
        """Return a rejection reason, or None if the order may proceed.

        `qty` is contracts-per-leg. `snap_ts` is the oldest backing-snapshot time
        across the legs (for the staleness breaker). Checks are ordered
        cheapest/most-critical first.
        """
        s = self.safety
        now = now or time.time()

        if s.kill_engaged():
            return "KILL switch engaged"
        if qty <= 0:
            return "size is zero"

        # circuit breakers
        if self.state.consecutive_errors >= s.max_consecutive_errors:
            return f"consecutive errors >= {s.max_consecutive_errors}"
        if self.state.orders_placed >= s.max_orders_per_session:
            return f"session order cap {s.max_orders_per_session} reached"
        if self.state.realized_loss >= s.daily_loss_limit_usd:
            return f"daily loss limit ${s.daily_loss_limit_usd} hit"

        # medium-band + edge guards
        if not (s.min_consensus <= opp.consensus <= s.max_consensus):
            return f"consensus {opp.consensus:.2f} outside band [{s.min_consensus},{s.max_consensus}]"

        # per-leg checks
        for leg in opp.legs:
            price_cents = int(round(leg.price * 100))
            if price_cents > s.max_price_cents:
                return f"price {price_cents}c exceeds max {s.max_price_cents}c"
            if qty > s.max_contracts_per_order:
                return f"qty {qty} exceeds per-order cap {s.max_contracts_per_order}"
        # feed staleness (oldest snapshot backing this opportunity)
        if snap_ts is not None and (now - snap_ts) > s.feed_staleness_seconds:
            return f"stale feed ({now - snap_ts:.0f}s > {s.feed_staleness_seconds}s)"

        # notional caps
        leg_notional = {leg.market_id: leg.price * qty for leg in opp.legs}
        group_add = sum(leg_notional.values())
        for mid, add in leg_notional.items():
            if self.state.market_notional.get(mid, 0.0) + add > s.max_notional_per_market_usd:
                return f"per-market notional cap ${s.max_notional_per_market_usd} for {mid}"
        if self.state.group_notional.get(opp.group_key, 0.0) + group_add > s.max_notional_per_group_usd:
            return f"per-group notional cap ${s.max_notional_per_group_usd}"
        if self.state.total_notional + group_add > s.max_total_notional_usd:
            return f"total notional cap ${s.max_total_notional_usd}"

        return None

    def live_guard(self, opp: Opportunity, venue_env: str, run_live_flag: bool) -> str | None:
        """Extra gate specifically for REAL orders (beyond check())."""
        s = self.safety
        if not s.live_allowed(venue_env, run_live_flag):
            return "live not allowed (need allow_live + prod env + --live + no kill)"
        if s.live_riskless_only and opp.kind != "dutch_book":
            return "LIVE_RISKLESS_ONLY: real money only on dutch-book locks"
        if opp.edge < s.min_edge_live:
            return f"edge {opp.edge:.3f} below live floor {s.min_edge_live}"
        if opp.matcher == "cluster" and opp.trust < s.cluster_trust_floor:
            return f"cluster trust {opp.trust:.2f} below floor {s.cluster_trust_floor}"
        return None

    # ---- bookkeeping ----------------------------------------------------
    def record_fill(self, opp: Opportunity, qty: int) -> None:
        for leg in opp.legs:
            add = leg.price * qty
            self.state.market_notional[leg.market_id] = self.state.market_notional.get(leg.market_id, 0.0) + add
            self.state.total_notional += add
        self.state.group_notional[opp.group_key] = (
            self.state.group_notional.get(opp.group_key, 0.0) + sum(leg.price * qty for leg in opp.legs)
        )
        self.state.orders_placed += 1
        self.state.consecutive_errors = 0

    def note_error(self) -> None:
        self.state.consecutive_errors += 1
        if self.state.consecutive_errors >= self.safety.max_consecutive_errors:
            # engage the file kill switch so a restart also stays halted.
            try:
                self.safety.kill_file.parent.mkdir(parents=True, exist_ok=True)
                self.safety.kill_file.touch()
                log.error("consecutive-error circuit breaker -> wrote KILL file")
            except OSError:
                pass
