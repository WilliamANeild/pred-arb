#!/usr/bin/env python3
"""Live tick recorder for MLB cross-venue pairs. Read-only: Polymarket via public
WebSocket, Kalshi via public fast REST polling. No keys, no orders.

  python scripts/mlb_pairs.py                    # first, discover pairs
  python scripts/stream_record.py --minutes 60   # then record a game window

Writes data/ticks/<session>.jsonl for scripts/analyze_dislocation.py.
"""
import argparse
import json
import time

import _bootstrap  # noqa: F401

from predarb.common.config import DATA_DIR
from predarb.research.pairs import Pair
from predarb.stream.cache import BookCache
from predarb.stream.kalshi_poll import KalshiPoller
from predarb.stream.polymarket_ws import PolymarketStream
from predarb.stream.recorder import TickRecorder


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--session", default=None, help="output filename stem")
    ap.add_argument("--poll", type=float, default=0.4, help="kalshi poll interval (s)")
    args = ap.parse_args()

    pairs_path = DATA_DIR / "mlb_pairs.json"
    if not pairs_path.exists():
        raise SystemExit("no data/mlb_pairs.json — run scripts/mlb_pairs.py first")
    pairs = [Pair.from_dict(d) for d in json.load(open(pairs_path))]
    if not pairs:
        raise SystemExit("mlb_pairs.json is empty — re-run scripts/mlb_pairs.py near game time")

    tickers = sorted({p.kalshi_ticker for p in pairs})
    tokens = sorted({p.poly_token for p in pairs})
    session = args.session or f"mlb_{int(time.time())}"
    print(f"recording {len(pairs)} pairs: {len(tickers)} kalshi tickers, {len(tokens)} poly tokens")

    cache = BookCache()
    rec = TickRecorder(cache, session)
    poly = PolymarketStream(tokens, cache).start()
    kal = KalshiPoller(tickers, cache, interval_s=args.poll).start()

    deadline = time.time() + args.minutes * 60
    try:
        while time.time() < deadline:
            time.sleep(5)
            print(f"  ... {rec.count} ticks recorded", end="\r")
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        poly.stop()
        kal.stop()
        rec.close()
    print(f"\ndone -> {rec.path}")


if __name__ == "__main__":
    main()
