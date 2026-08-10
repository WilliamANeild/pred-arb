#!/usr/bin/env python3
"""Paper-trade the live feed: scan -> size -> simulate fills through the SAME safety
gate the live executor uses. No real money can be placed by this script.

  python scripts/paper_trade.py --matcher intraevent --profile both
"""
import argparse

import _bootstrap  # noqa: F401

from predarb.common.config import SafetyConfig, load_params
from predarb.execute.paper import new_paper_broker
from predarb.matching import build_matcher
from predarb.signal.profiles import build_profile
from predarb.sizing.confidence import size_opportunity
from predarb.venues.registry import build_adapters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matcher", default="intraevent", choices=["curated", "intraevent", "cluster"])
    ap.add_argument("--profile", default="both", choices=["riskless_only", "relative_value", "both"])
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    params, safety = load_params(), SafetyConfig()
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
    wanted = {m.key for g in groups for m in g.members}
    snaps = {}
    for a in adapters.values():
        for r in a.list_markets(limit=args.limit):
            if r.key in wanted:
                try:
                    snaps[r.key] = a.get_snapshot(r)
                except Exception:  # noqa: BLE001
                    pass

    broker = new_paper_broker(safety, params)
    profile = build_profile(args.profile)
    for g in groups:
        for opp in profile.evaluate(g, snaps, params, safety):
            qty = size_opportunity(opp, safety, params)
            if qty > 0:
                broker.execute(opp, qty, snaps)

    print(f"\n=== paper session ===")
    print(f"filled: {len(broker.report.filled)}   deployed: ${broker.report.deployed_usd:.2f}")
    for o in broker.report.filled:
        print(f"  {o.group_key}: buy {o.side} {o.market_id} x{o.qty} @ {o.price:.3f} (${o.cost_usd:.2f})")
    if broker.report.blocked:
        print(f"blocked ({len(broker.report.blocked)}):")
        for b in broker.report.blocked[:20]:
            print(f"  {b}")


if __name__ == "__main__":
    main()
