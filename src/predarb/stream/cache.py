"""Thread-safe live book cache. Producers (WS client, poller) call `update`;
a top-of-book change fires the registered callbacks (the recorder logs a tick)."""
from __future__ import annotations

import threading

from ..common.types import Book


class BookCache:
    def __init__(self):
        self._d: dict[str, tuple[Book, float]] = {}
        self._top: dict[str, tuple] = {}
        self._lock = threading.Lock()
        self._cbs = []

    def on_update(self, cb):
        """cb(venue, market_id, book, ts) — fired only when top-of-book changes."""
        self._cbs.append(cb)

    def update(self, venue: str, market_id: str, book: Book, ts: float) -> None:
        key = f"{venue}:{market_id}"
        top = (book.yes_bid, book.yes_ask)
        with self._lock:
            changed = self._top.get(key) != top
            self._d[key] = (book, ts)
            self._top[key] = top
        if changed:
            for cb in self._cbs:
                try:
                    cb(venue, market_id, book, ts)
                except Exception:  # noqa: BLE001 — a bad callback must not kill the feed
                    pass

    def get(self, key: str) -> tuple[Book, float] | None:
        with self._lock:
            return self._d.get(key)

    def snapshot(self) -> dict[str, tuple[Book, float]]:
        with self._lock:
            return dict(self._d)
