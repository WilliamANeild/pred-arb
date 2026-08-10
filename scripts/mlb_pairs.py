#!/usr/bin/env python3
"""Discover identical MLB market pairs across Kalshi + Polymarket and save them to
data/mlb_pairs.json for the recorder. Read-only.

  python scripts/mlb_pairs.py
"""
import json

import _bootstrap  # noqa: F401

from predarb.common.config import DATA_DIR
from predarb.research.mlb import discover_mlb_pairs


def main():
    pairs = discover_mlb_pairs()
    print(f"discovered {len(pairs)} MLB cross-venue pairs:\n")
    for p in pairs:
        print(f"  [{p.kind}] {p.label}")
        print(f"      kalshi={p.kalshi_ticker}  poly={p.poly_token[:16]}...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "mlb_pairs.json"
    with open(path, "w") as f:
        json.dump([p.to_dict() for p in pairs], f, indent=2)
    print(f"\nsaved -> {path}")
    if not pairs:
        print("\n(no pairs right now — likely no overlapping liquid MLB games. "
              "Re-run near/at game time.)")


if __name__ == "__main__":
    main()
