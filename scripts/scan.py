#!/usr/bin/env python3
"""Read-only live opportunity scan. No orders, no keys required for reads.

  python scripts/scan.py --matcher intraevent --profile both
  python scripts/scan.py --list kalshi           # dump discoverable markets
"""
import argparse

import _bootstrap  # noqa: F401

from predarb.common.config import SafetyConfig, load_params
from predarb.matching import build_matcher
from predarb.sizing.confidence import size_opportunity
from predarb.signal.profiles import build_profile
from predarb.venues.registry import build_adapters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matcher", default="intraevent", choices=["curated", "intraevent", "cluster"])
    ap.add_argument("--profile", default="both", choices=["riskless_only", "relative_value", "both"])
    ap.add_argument("--limit", type=int, default=200, help="markets to pull per venue")
    ap.add_argument("--list", metavar="VENUE", help="just list markets for a venue and exit")
    args = ap.parse_args()

    adapters = build_adapters()
    if not adapters:
        raise SystemExit("no venue adapters available")

    if args.list:
        a = adapters.get(args.list)
        if not a:
            raise SystemExit(f"no adapter {args.list}; have {list(adapters)}")
        for r in a.list_markets(limit=args.limit)[:args.limit]:
            print(f"{r.venue:<11} {r.market_id:<28} {r.event_id:<18} {r.title[:50]}")
        return

    params, safety = load_params(), SafetyConfig()

    refs = []
    for a in adapters.values():
        try:
            refs += a.list_markets(limit=args.limit)
        except Exception as e:  # noqa: BLE001
            print(f"! {a.name} list_markets failed: {e}")
    print(f"discovered {len(refs)} markets across {list(adapters)}")

    groups = build_matcher(args.matcher).build(refs)
    print(f"{args.matcher} matcher -> {len(groups)} groups")

    # snapshot only the markets that belong to a group
    wanted = {m.key for g in groups for m in g.members}
    snaps = {}
    for a in adapters.values():
        for r in a.list_markets(limit=args.limit):
            if r.key in wanted:
                try:
                    snaps[r.key] = a.get_snapshot(r)
                except Exception:  # noqa: BLE001
                    pass

    profile = build_profile(args.profile)
    found = 0
    for g in groups:
        for opp in profile.evaluate(g, snaps, params, safety):
            qty = size_opportunity(opp, safety, params)
            found += 1
            print(f"\n[{opp.kind}] {g.key}  edge={opp.edge:+.3f} conf={opp.confidence:.2f} "
                  f"consensus={opp.consensus:.2f} disp={opp.dispersion:.3f} size={qty}")
            for leg in opp.legs:
                print(f"    buy {leg.side:<3} {leg.venue}:{leg.market_id} @ {leg.price:.3f}")
            print(f"    {opp.note}")
    print(f"\n{found} opportunities (READ-ONLY — nothing placed).")


if __name__ == "__main__":
    main()
