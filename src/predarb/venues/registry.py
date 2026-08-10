"""Venue registry — build the set of adapters enabled by config."""
from __future__ import annotations

from ..common.config import polymarket as poly_cfg
from ..common.logenv import get_logger
from .base import VenueAdapter

log = get_logger("venues.registry")


def build_adapters(*, include_polymarket: bool | None = None) -> dict[str, VenueAdapter]:
    """Instantiate available venue adapters. Import lazily so a missing optional
    dependency (or network) never breaks the others."""
    adapters: dict[str, VenueAdapter] = {}
    try:
        from .kalshi import KalshiAdapter
        adapters["kalshi"] = KalshiAdapter()
    except Exception as e:  # noqa: BLE001
        log.warning("kalshi adapter unavailable: %s", e)

    want_poly = poly_cfg.enabled if include_polymarket is None else include_polymarket
    if want_poly:
        try:
            from .polymarket import PolymarketAdapter
            adapters["polymarket"] = PolymarketAdapter()
        except Exception as e:  # noqa: BLE001
            log.warning("polymarket adapter unavailable: %s", e)

    return adapters
