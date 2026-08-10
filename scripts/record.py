#!/usr/bin/env python3
"""Record real market snapshots into data/snapshots.jsonl to build a backtest set.

Read-only; needs no API keys. Snapshots the markets that belong to groups under the
chosen matcher (so the recording is aligned with what we'd actually trade).

  python scripts/record.py --minutes 60 --interval 15 --matcher intraevent
"""
import argparse

import _bootstrap  # noqa: F401

from predarb.matching import build_matcher
from predarb.recorder.snapshot import Recorder
from predarb.venues.registry import build_adapters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--interval", type=float, default=15.0, help="seconds between polls")
    ap.add_argument("--matcher", default="intraevent", choices=["curated", "intraevent", "cluster"])
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    adapters = build_adapters()
    if not adapters:
        raise SystemExit("no venue adapters available")

    refs = []
    for a in adapters.values():
        try:
            refs += a.list_markets(limit=args.limit)
        except Exception as e:  # noqa: BLE001
            print(f"! {a.name} list_markets failed: {e}")

    groups = build_matcher(args.matcher).build(refs)
    wanted_keys = {m.key for g in groups for m in g.members}
    grouped_refs = [r for r in refs if r.key in wanted_keys]
    print(f"recording {len(grouped_refs)} markets in {len(groups)} groups "
          f"every {args.interval}s for {args.minutes} min")

    Recorder(adapters, grouped_refs).run(minutes=args.minutes, interval_s=args.interval)


if __name__ == "__main__":
    main()
