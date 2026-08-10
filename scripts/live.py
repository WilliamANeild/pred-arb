#!/usr/bin/env python3
"""Run the live engine across every configured venue.

Paper by default (simulated fills through the leg-risk executor). Live is fenced
off until fill-confirmation is wired; --live will refuse rather than guess a fill.

  python scripts/live.py --matcher intraevent --profile both --cycles 5
  python scripts/live.py --minutes 30 --interval 10
"""
import argparse

import _bootstrap  # noqa: F401

from predarb.common.config import SafetyConfig, load_params
from predarb.engine.live import LiveEngine
from predarb.venues.registry import build_adapters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matcher", default="intraevent", choices=["curated", "intraevent", "cluster"])
    ap.add_argument("--profile", default="both", choices=["riskless_only", "relative_value", "both"])
    ap.add_argument("--cycles", type=int, default=3)
    ap.add_argument("--minutes", type=float, default=None)
    ap.add_argument("--interval", type=float, default=10.0)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--live", action="store_true", help="attempt REAL orders (hard-gated)")
    args = ap.parse_args()

    adapters = build_adapters()
    if not adapters:
        raise SystemExit("no venue adapters available")
    print(f"venues: {[(n, a.market_type, 'exec' if a.supports_trading() else 'read') for n, a in adapters.items()]}")

    backend = None
    if args.live:
        from predarb.execute.backends import LiveBackend
        backend = LiveBackend(adapters)
        print("!! --live requested: LiveBackend is fenced off until fill-confirmation is built.")

    engine = LiveEngine(adapters, matcher=args.matcher, profile=args.profile,
                        params=load_params(), safety=SafetyConfig(),
                        backend=backend, live=args.live)
    rep = engine.run(cycles=args.cycles, minutes=args.minutes, interval_s=args.interval, limit=args.limit)

    print(f"\n=== session ===")
    print(f"cycles: {rep.cycles}   filled: {rep.filled}   deployed: ${rep.deployed_usd:.2f}   unwound: {rep.unwound}")
    for b in rep.blocked[:20]:
        print(f"  blocked: {b}")


if __name__ == "__main__":
    main()
