"""Realistic fill simulation: walk the orderbook, VWAP, partial fills, phantom
haircut, and fees. Never fill against midprice. Prices are in probability units.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..signal.fees import kalshi_fee_usd


@dataclass
class Fill:
    filled: int              # contracts actually filled
    avg_price: float         # volume-weighted fill price (prob)
    fee_usd: float
    cost_usd: float          # contracts*price + fee (what you pay to enter)
    slippage: float          # avg fill vs. best level (prob)


def walk_book(levels: list[tuple[float, int]], want: int, haircut: float) -> tuple[int, float]:
    """Consume ascending-price ask levels up to `want` contracts, applying a
    per-level availability haircut. Returns (filled, vwap_prob)."""
    filled, notional = 0, 0.0
    for price, qty in levels:
        avail = int(qty * haircut)
        if avail <= 0:
            continue
        take = min(avail, want - filled)
        filled += take
        notional += take * price
        if filled >= want:
            break
    vwap = notional / filled if filled else 0.0
    return filled, vwap


def simulate_fill(ask_levels: list[tuple[float, int]], want: int, *, venue: str = "kalshi",
                  haircut: float = 0.5, fee_rate: float = 0.07) -> Fill:
    """Simulate a marketable BUY crossing the given ask ladder (prob units)."""
    if not ask_levels or want <= 0:
        return Fill(0, 0.0, 0.0, 0.0, 0.0)
    filled, vwap = walk_book(ask_levels, want, haircut)
    if filled == 0:
        return Fill(0, 0.0, 0.0, 0.0, 0.0)
    fee_usd = kalshi_fee_usd(vwap, filled, fee_rate) if venue == "kalshi" else 0.0
    cost_usd = filled * vwap + fee_usd
    best = ask_levels[0][0]
    return Fill(filled, vwap, fee_usd, cost_usd, vwap - best)
