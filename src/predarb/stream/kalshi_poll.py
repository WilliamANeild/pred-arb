"""Kalshi fast REST poller (public, no key). Kalshi's WebSocket requires auth, so
until a key exists we poll the order book of a small watch-list quickly. For a
handful of MLB markets this captures second-scale dislocations. Swappable for a
Kalshi WS client later with no downstream change (it just feeds the same cache).
"""
from __future__ import annotations

import threading
import time

from ..common.logenv import get_logger
from ..common.types import Book
from ..venues.kalshi_client import KalshiClient
from .cache import BookCache

log = get_logger("stream.kalshi")


class KalshiPoller:
    def __init__(self, tickers: list[str], cache: BookCache, *, interval_s: float = 0.4,
                 client: KalshiClient | None = None):
        self.tickers = list(tickers)
        self.cache = cache
        self.interval_s = interval_s
        self.client = client or KalshiClient()
        self._thread = None
        self._stop = False

    def _poll_one(self, ticker: str):
        ob = self.client.get_orderbook(ticker)
        asks = [(c / 100.0, q) for c, q in ob.yes_ask_levels()]
        bids = [(c / 100.0, q) for c, q in ob.yes_bid_levels()]
        book = Book(yes_ask=asks[0][0] if asks else None,
                    yes_bid=bids[0][0] if bids else None,
                    yes_ask_levels=asks, yes_bid_levels=bids)
        self.cache.update("kalshi", ticker, book, time.time())

    def start(self):
        def run():
            while not self._stop:
                for tk in self.tickers:
                    if self._stop:
                        break
                    try:
                        self._poll_one(tk)
                    except Exception as e:  # noqa: BLE001
                        log.warning("poll %s failed: %s", tk, e)
                    time.sleep(self.interval_s)
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop = True
