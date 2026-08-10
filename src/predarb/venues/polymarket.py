"""Polymarket VenueAdapter — read-only market data (Gamma + CLOB).

Reads need no auth. Prices are already in probability units (0..1) on Polymarket,
so normalization is a straight pass-through. Trading is intentionally NOT
implemented in the POC: it requires an L2-signed API key plus a funded USDC wallet
and on-chain settlement, which we add only after the strategy proves out.
"""
from __future__ import annotations

import time

import requests

from ..common.config import PolymarketConfig, polymarket as default_cfg
from ..common.logenv import get_logger
from ..common.types import Book, MarketRef, Snapshot
from .base import VenueAdapter

log = get_logger("venues.polymarket")


class PolymarketAdapter(VenueAdapter):
    name = "polymarket"
    env = "prod"          # Polymarket has no demo; reads are harmless, trading stays disabled
    market_type = "orderbook"
    executable = False    # read-only in the POC (trading needs a funded USDC wallet + L2 key)

    def __init__(self, cfg: PolymarketConfig | None = None, session: requests.Session | None = None):
        self.cfg = cfg or default_cfg
        self.session = session or requests.Session()

    def _get(self, base: str, path: str, **params) -> dict | list:
        r = self.session.get(base + path, params=params or None, timeout=20)
        r.raise_for_status()
        return r.json() if r.content else {}

    def list_markets(self, *, limit=100, active=True, closed=False, **_) -> list[MarketRef]:
        data = self._get(self.cfg.gamma_url, "/markets",
                         limit=limit, active=str(active).lower(), closed=str(closed).lower())
        rows = data if isinstance(data, list) else data.get("data", [])
        out = []
        for m in rows:
            # A Gamma "market" has clobTokenIds (YES/NO outcome token ids).
            token_ids = m.get("clobTokenIds") or []
            if isinstance(token_ids, str):
                import json
                try:
                    token_ids = json.loads(token_ids)
                except Exception:  # noqa: BLE001
                    token_ids = []
            yes_token = token_ids[0] if token_ids else m.get("id", "")
            out.append(MarketRef(
                venue=self.name,
                market_id=str(yes_token),
                title=m.get("question", "") or m.get("title", ""),
                event_id=str(m.get("conditionId", "") or m.get("groupItemTitle", "")),
                yes_meaning=(m.get("outcomes") or ["Yes"])[0] if m.get("outcomes") else "Yes",
            ))
        return out

    def get_snapshot(self, ref: MarketRef) -> Snapshot:
        # CLOB book keyed by YES outcome token id. Bids/asks already in prob (USDC).
        book_json = self._get(self.cfg.clob_url, "/book", token_id=ref.market_id)
        bids = [(float(b["price"]), int(float(b["size"]))) for b in book_json.get("bids", [])]
        asks = [(float(a["price"]), int(float(a["size"]))) for a in book_json.get("asks", [])]
        bids.sort(key=lambda x: -x[0])
        asks.sort(key=lambda x: x[0])
        book = Book(
            yes_ask=asks[0][0] if asks else None,
            yes_bid=bids[0][0] if bids else None,
            yes_ask_levels=asks,
            yes_bid_levels=bids,
        )
        return Snapshot(ref=ref, book=book, ts=time.time())

    def supports_trading(self) -> bool:
        return False   # read-only in the POC
