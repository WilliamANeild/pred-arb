"""Fee models, in probability units per contract.

A binary contract settles at $1, so an edge measured in probability units equals
an edge in dollars per contract. Fees are folded in the same units. Kalshi charges
a taker fee ~ rate * p * (1-p); Polymarket has no per-trade fee (2026).
"""
from __future__ import annotations

import math


def fee_per_contract(venue: str, price: float, params: dict) -> float:
    """Approximate per-contract fee in probability units (used for signal edges)."""
    p = max(0.0, min(1.0, price))
    if venue == "kalshi":
        return params.get("kalshi_fee_rate", 0.07) * p * (1.0 - p)
    if venue == "polymarket":
        return params.get("polymarket_fee_rate", 0.0) * p * (1.0 - p)
    return 0.0


def kalshi_fee_usd(price: float, qty: int, rate: float = 0.07) -> float:
    """Exact Kalshi taker fee in dollars for a fill (ceil to the cent)."""
    p = max(0.0, min(1.0, price))
    return math.ceil(rate * qty * p * (1.0 - p) * 100) / 100.0
