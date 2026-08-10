"""Confidence-weighted position sizing.

Real money is sized per trade by confidence, as requested. A dutch-book lock is
structurally certain (confidence ~ 1); a relative-value trade's confidence scales
with its edge and is dampened by the matcher's trust (cluster groups size smallest).
Final size is fractional-Kelly * confidence * bankroll, then clamped by every hard
cap in SafetyConfig.
"""
from __future__ import annotations

from ..common.config import SafetyConfig
from ..common.types import Opportunity


def kelly_fraction(p_win: float, price: float) -> float:
    """Kelly stake fraction for a binary contract bought at prob `price`.
    Payoff win +$(1-price), lose -$price -> f* = (p_win - price) / (1 - price)."""
    if price <= 0 or price >= 1:
        return 0.0
    f = (p_win - price) / (1.0 - price)
    return max(0.0, min(1.0, f))


def confidence(opp: Opportunity, params: dict) -> float:
    """0..1 confidence for the opportunity, before Kelly."""
    if opp.kind == "dutch_book":
        base = 1.0
    else:
        # scale edge into [0,1]; an edge of 2x the min threshold saturates.
        denom = max(2.0 * params["relval_min_edge"], 1e-6)
        base = max(0.0, min(1.0, opp.edge / denom))
    conf = base * max(0.0, min(1.0, opp.trust))
    if opp.matcher == "cluster":
        conf *= params.get("cluster_trust", 0.6)   # dampen the least-trusted matcher
    return conf


def size_opportunity(opp: Opportunity, safety: SafetyConfig, params: dict) -> int:
    """Set opp.confidence and return the number of contracts per leg (0 = skip).

    All legs of a lock trade the same qty (they must, to stay balanced). The
    returned qty is already clamped by depth (with a phantom haircut) and by the
    per-order / per-market / per-group / total-notional caps.
    """
    conf = confidence(opp, params)
    opp.confidence = conf
    if conf < params["confidence_floor"]:
        return 0

    # Kelly on the priciest leg (the binding one for a lock).
    price = max(leg.price for leg in opp.legs)
    f = kelly_fraction(opp.p_win, price) if opp.kind != "dutch_book" else 1.0
    f *= params["kelly_fraction"] * conf
    if f <= 0:
        return 0

    # cost to put on ONE unit of the whole position (sum of leg entry prices).
    cost_per_unit = sum(leg.price for leg in opp.legs) or 0.01

    kelly_contracts = int((f * safety.bankroll_usd) / cost_per_unit)

    # depth cap: min shown depth across legs, phantom-haircut.
    depth = min(int(leg.qty * params["phantom_haircut"]) for leg in opp.legs)

    # notional caps.
    per_market = int(safety.max_notional_per_market_usd / max(price, 0.01))
    per_group = int(safety.max_notional_per_group_usd / max(cost_per_unit, 0.01))

    qty = min(kelly_contracts, depth, per_market, per_group,
              safety.max_contracts_per_order)
    return max(0, qty)
