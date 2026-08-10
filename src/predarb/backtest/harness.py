"""Replay harness — walk a recorded/synthetic timeline frame by frame, open
positions when a profile signals, and close them on convergence or at settlement.

The SAME SafetyGate, sizing, and fill model the live path uses run here, so a
backtest is a faithful dry run of production rather than a separate code path.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..common.config import SafetyConfig
from ..common.types import Leg, MarketGroup, Opportunity, Snapshot
from ..execute.safety import GateState, SafetyGate
from ..signal.consensus import compute_consensus
from ..signal.fees import kalshi_fee_usd
from ..sizing.confidence import size_opportunity
from .fills import simulate_fill
from .metrics import Metrics, compute_metrics
from .trade import BacktestTrade


@dataclass
class OpenPos:
    opp: Opportunity
    group: MarketGroup
    qty: int
    entry_ts: float
    entry_cost: float


def _entry_cost(opp: Opportunity, qty: int, snaps: dict[str, Snapshot], params: dict) -> float | None:
    """Simulate entering every leg at qty. Return total USD cost, or None if any
    leg can't be fully filled (we never hold an unbalanced lock)."""
    total = 0.0
    for leg in opp.legs:
        snap = snaps.get(f"{leg.venue}:{leg.market_id}")
        if snap is None:
            return None
        levels = snap.book.yes_ask_levels if leg.side == "yes" else snap.book.no_ask_levels()
        fill = simulate_fill(levels, qty, venue=leg.venue,
                             haircut=params["phantom_haircut"], fee_rate=params["kalshi_fee_rate"])
        if fill.filled < qty:
            return None
        total += fill.cost_usd
    return total


def _sell_one(leg: Leg, qty: int, snaps: dict[str, Snapshot], params: dict) -> float:
    """Proceeds from unwinding one leg at the current best bid (fee-adjusted)."""
    snap = snaps.get(f"{leg.venue}:{leg.market_id}")
    if snap is None:
        return 0.0
    if leg.side == "yes":
        price = snap.book.yes_bid or 0.0
    else:  # we hold NO; sell NO at NO-bid = 1 - yes_ask
        price = 1.0 - (snap.book.yes_ask if snap.book.yes_ask is not None else 1.0)
    fee = kalshi_fee_usd(price, qty, params["kalshi_fee_rate"]) if leg.venue == "kalshi" else 0.0
    return max(0.0, qty * price - fee)


def _settle_payoff(pos: OpenPos, snaps: dict[str, Snapshot], settle_map: dict[str, float],
                   params: dict) -> float:
    """Payoff at resolution. Uses known settlement where available; otherwise marks
    the leg to market. For a correct grouping a lock returns ~qty regardless of
    outcome; for a WRONG (e.g. cluster) grouping the legs settle independently and
    the loss shows up here — which is exactly the basis risk we want measured."""
    payoff = 0.0
    for leg in pos.opp.legs:
        key = f"{leg.venue}:{leg.market_id}"
        st = settle_map.get(key)
        if st is None:
            payoff += _sell_one(leg, pos.qty, snaps, params)
        else:
            win = (leg.side == "yes" and st >= 0.5) or (leg.side == "no" and st < 0.5)
            payoff += pos.qty if win else 0.0
    return payoff


def _close(pos: OpenPos, payoff: float, ts: float, kind: str,
           matcher: str, profile: str) -> BacktestTrade:
    return BacktestTrade(
        group_key=pos.group.key, matcher=matcher, profile=profile, kind=pos.opp.kind,
        qty=pos.qty, cost_usd=pos.entry_cost, payoff_usd=payoff,
        entry_ts=pos.entry_ts, exit_ts=ts, exit_kind=kind,
        edge_expected=pos.opp.edge, legs=list(pos.opp.legs),
    )


def run_backtest(frames, groups: list[MarketGroup], profile, params: dict,
                 safety: SafetyConfig, matcher_name: str) -> list[BacktestTrade]:
    gate = SafetyGate(safety, GateState())
    open_pos: dict[str, OpenPos] = {}
    trades: list[BacktestTrade] = []
    settle_map: dict[str, float] = {}
    n = len(frames)

    for fi, frame in enumerate(frames):
        snaps = frame.snaps
        for key, s in snaps.items():
            if s.settle is not None:
                settle_map[key] = s.settle
        is_last = fi == n - 1

        # 1. convergence exits for open relative-value positions
        for gk, pos in list(open_pos.items()):
            if pos.opp.kind != "relative_value" or is_last:
                continue
            cons = compute_consensus(pos.group, snaps, params)
            if cons is None:
                continue
            held = pos.opp.legs[0].market_id
            view = next((v for v in cons.views if v.member.market_id == held), None)
            if view is not None and abs(view.deviation) <= params["close_deviation"]:
                payoff = sum(_sell_one(leg, pos.qty, snaps, params) for leg in pos.opp.legs)
                trades.append(_close(pos, payoff, frame.ts, "converge", matcher_name, profile.name))
                del open_pos[gk]

        # 2. open new positions
        for grp in groups:
            if grp.key in open_pos:
                continue
            opps = profile.evaluate(grp, snaps, params, safety)
            if not opps:
                continue
            opp = max(opps, key=lambda o: o.edge)
            qty = size_opportunity(opp, safety, params)
            if qty <= 0:
                continue
            if gate.check(opp, qty, snap_ts=frame.ts, now=frame.ts) is not None:
                continue
            cost = _entry_cost(opp, qty, snaps, params)
            if cost is None:
                continue
            gate.record_fill(opp, qty)
            open_pos[grp.key] = OpenPos(opp=opp, group=grp, qty=qty,
                                        entry_ts=frame.ts, entry_cost=cost)

    # 3. settle everything still open at the last frame
    last = frames[-1]
    for pos in open_pos.values():
        payoff = _settle_payoff(pos, last.snaps, settle_map, params)
        trades.append(_close(pos, payoff, last.ts, "settle", matcher_name, profile.name))

    return trades


def backtest_metrics(frames, groups, profile, params, safety, matcher_name) -> tuple[list[BacktestTrade], Metrics]:
    trades = run_backtest(frames, groups, profile, params, safety, matcher_name)
    return trades, compute_metrics(trades)
