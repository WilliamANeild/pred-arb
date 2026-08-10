"""Snapshot store — append recorded market frames to JSONL and read them back as a
backtest timeline. One JSONL line = one poll cycle (a "frame") holding every
market's book at that instant, so the backtester can replay frame by frame.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..common.config import DATA_DIR
from ..common.types import Book, MarketRef, Snapshot


def snapshot_to_row(s: Snapshot) -> dict:
    return {
        "venue": s.ref.venue, "market_id": s.ref.market_id, "title": s.ref.title,
        "event_id": s.ref.event_id, "yes_meaning": s.ref.yes_meaning,
        "yes_bid": s.book.yes_bid, "yes_ask": s.book.yes_ask,
        "yes_ask_levels": s.book.yes_ask_levels, "yes_bid_levels": s.book.yes_bid_levels,
        "settle": s.settle,
    }


def row_to_snapshot(row: dict, ts: float) -> Snapshot:
    ref = MarketRef(venue=row["venue"], market_id=row["market_id"], title=row.get("title", ""),
                    event_id=row.get("event_id", ""), yes_meaning=row.get("yes_meaning", ""))
    book = Book(
        yes_bid=row.get("yes_bid"), yes_ask=row.get("yes_ask"),
        yes_ask_levels=[tuple(x) for x in row.get("yes_ask_levels", [])],
        yes_bid_levels=[tuple(x) for x in row.get("yes_bid_levels", [])],
    )
    return Snapshot(ref=ref, book=book, ts=ts, settle=row.get("settle"))


@dataclass
class Frame:
    ts: float
    snaps: dict[str, Snapshot]   # keyed by "venue:market_id"


class SnapshotStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DATA_DIR / "snapshots.jsonl"

    def append_frame(self, ts: float, snaps: list[Snapshot]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": ts, "snaps": [snapshot_to_row(s) for s in snaps]}
        with open(self.path, "a") as f:
            f.write(json.dumps(row) + "\n")

    def load_frames(self) -> list[Frame]:
        if not self.path.exists():
            return []
        frames = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                ts = obj["ts"]
                snaps = {}
                for r in obj["snaps"]:
                    s = row_to_snapshot(r, ts)
                    snaps[s.ref.key] = s
                frames.append(Frame(ts=ts, snaps=snaps))
        return frames
