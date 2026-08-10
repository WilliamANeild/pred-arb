"""Tick recorder — append every top-of-book change to data/ticks/<session>.jsonl.

One line per tick: {ts, venue, market_id, yes_bid, yes_ask}. This is the raw
material for the dislocation analysis: aligned, tick-level, cross-venue.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from ..common.config import DATA_DIR
from ..common.logenv import get_logger
from .cache import BookCache

log = get_logger("stream.recorder")


class TickRecorder:
    def __init__(self, cache: BookCache, session: str, out_dir: Path | None = None):
        self.dir = out_dir or (DATA_DIR / "ticks")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / f"{session}.jsonl"
        self._fh = open(self.path, "a")
        self._lock = threading.Lock()
        self.count = 0
        cache.on_update(self._on_update)

    def _on_update(self, venue, market_id, book, ts):
        row = {"ts": round(ts, 3), "venue": venue, "market_id": market_id,
               "yes_bid": book.yes_bid, "yes_ask": book.yes_ask}
        with self._lock:
            self._fh.write(json.dumps(row) + "\n")
            self._fh.flush()
            self.count += 1

    def close(self):
        with self._lock:
            self._fh.close()
        log.info("recorded %d ticks -> %s", self.count, self.path)
