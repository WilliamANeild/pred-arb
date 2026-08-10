"""Kalshi VenueAdapter — wraps KalshiClient and normalizes to probability units."""
from __future__ import annotations

import time

from ..common.config import KalshiConfig, kalshi as default_cfg
from ..common.types import Book, Leg, MarketRef, Snapshot
from .base import VenueAdapter
from .kalshi_client import KalshiClient


def _cents_levels_to_prob(levels: list[tuple[int, int]]) -> list[tuple[float, int]]:
    return [(c / 100.0, q) for c, q in levels]


class KalshiAdapter(VenueAdapter):
    name = "kalshi"
    market_type = "orderbook"
    executable = True   # order book; actual trading still requires creds (see supports_trading)

    def __init__(self, cfg: KalshiConfig | None = None, client: KalshiClient | None = None):
        self.cfg = cfg or default_cfg
        self.env = self.cfg.env
        self.client = client or KalshiClient(self.cfg)

    def list_markets(self, *, series_ticker=None, event_ticker=None, status="open",
                     limit=100, **_) -> list[MarketRef]:
        raw = self.client.iter_all_markets(
            series_ticker=series_ticker, event_ticker=event_ticker, status=status, limit=limit
        )
        out = []
        for m in raw:
            out.append(MarketRef(
                venue=self.name,
                market_id=m.get("ticker", ""),
                title=m.get("title") or m.get("yes_sub_title") or "",
                event_id=m.get("event_ticker", ""),
                yes_meaning=m.get("yes_sub_title", ""),
            ))
        return out

    def get_snapshot(self, ref: MarketRef) -> Snapshot:
        ob = self.client.get_orderbook(ref.market_id)
        ask_levels = _cents_levels_to_prob(ob.yes_ask_levels())
        bid_levels = _cents_levels_to_prob(ob.yes_bid_levels())
        book = Book(
            yes_ask=ask_levels[0][0] if ask_levels else None,
            yes_bid=bid_levels[0][0] if bid_levels else None,
            yes_ask_levels=ask_levels,
            yes_bid_levels=bid_levels,
        )
        return Snapshot(ref=ref, book=book, ts=time.time())

    def supports_trading(self) -> bool:
        return self.client.cfg.has_credentials()

    def place(self, leg: Leg, *, client_order_id: str | None = None) -> dict:
        # Convert normalized probability price back to Kalshi cents.
        price_cents = int(round(leg.price * 100))
        return self.client.create_order(
            ticker=leg.market_id, action="buy", side=leg.side, count=leg.qty,
            price_cents=price_cents, client_order_id=client_order_id,
        )
