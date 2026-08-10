"""Snapshotter — poll a set of markets across venues and persist frames.

Run it for a while (scripts/record.py) to build the real backtest dataset. It is
strictly read-only: it never places an order and needs no API keys.
"""
from __future__ import annotations

import time

from ..common.logenv import get_logger
from ..common.types import MarketRef, Snapshot
from ..venues.base import VenueAdapter
from .store import SnapshotStore

log = get_logger("recorder")


class Recorder:
    def __init__(self, adapters: dict[str, VenueAdapter], refs: list[MarketRef],
                 store: SnapshotStore | None = None):
        self.adapters = adapters
        self.refs = refs
        self.store = store or SnapshotStore()

    def poll_once(self) -> int:
        ts = time.time()
        snaps: list[Snapshot] = []
        for ref in self.refs:
            a = self.adapters.get(ref.venue)
            if a is None:
                continue
            try:
                snaps.append(a.get_snapshot(ref))
            except Exception as e:  # noqa: BLE001
                log.warning("snapshot failed %s: %s", ref.key, e)
        if snaps:
            self.store.append_frame(ts, snaps)
        return len(snaps)

    def run(self, *, minutes: float, interval_s: float = 10.0) -> None:
        deadline = time.time() + minutes * 60
        polls = 0
        while time.time() < deadline:
            n = self.poll_once()
            polls += 1
            log.info("poll %d: recorded %d snapshots", polls, n)
            time.sleep(interval_s)
        log.info("done: %d polls -> %s", polls, self.store.path)
