#!/usr/bin/env python3
"""Live edge scanner (read-only research). Two modes:

  python scripts/edge_scan.py dutch     # single-venue Kalshi intra-event dutch books
  python scripts/edge_scan.py cross     # cross-venue Kalshi<->Polymarket, equivalence-gated

`cross` uses the STRUCTURED equivalence guard so it reports only genuinely-identical
contracts (same threshold/direction/date) and separately shows the false matches it
rejected — the ones a naive title-matcher would have "found" and lost money on.

Results are written to data/edge_scan_<mode>.json. No orders are placed.
"""
import argparse
import json
import re
import time

import _bootstrap  # noqa: F401
import requests

from predarb.common.config import DATA_DIR
from predarb.signal.equivalence import is_equivalent
from predarb.venues.kalshi_client import KalshiClient


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


_STOP = set("will be to of in on at for and or is are by this that a an the who what "
            "when which whether reach hit close end price after before during".split())


def toks(s):
    return {x for x in re.findall(r"[a-z0-9]+", (s or "").lower()) if x not in _STOP and len(x) > 1}


def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def pull_kalshi_markets(max_pages=50):
    c = KalshiClient()
    out, cur, pg = [], None, 0
    while pg < max_pages:
        p = {"status": "open", "limit": 200}
        if cur:
            p["cursor"] = cur
        r = c._request("GET", "/markets", params=p)
        for m in r.get("markets", []):
            ya, yb = fnum(m.get("yes_ask_dollars")), fnum(m.get("yes_bid_dollars"))
            title = (m.get("title", "") + " " + m.get("yes_sub_title", "")).strip()
            out.append({"t": title, "tk": m.get("ticker"), "ask": ya, "bid": yb,
                        "event": m.get("event_ticker", "")})
        cur = r.get("cursor")
        pg += 1
        if not cur:
            break
    return out


def pull_polymarket(max_pages=6):
    out, off = [], 0
    for _ in range(max_pages):
        r = requests.get("https://gamma-api.polymarket.com/markets",
                         params={"limit": 500, "offset": off, "active": "true", "closed": "false",
                                 "order": "volume24hr", "ascending": "false"}, timeout=25).json()
        rows = r if isinstance(r, list) else r.get("data", [])
        if not rows:
            break
        for m in rows:
            ba, bb = fnum(m.get("bestAsk")), fnum(m.get("bestBid"))
            if ba is None or bb is None:
                continue
            out.append({"q": m.get("question", ""), "ask": ba, "bid": bb,
                        "liq": fnum(m.get("liquidity")) or 0})
        off += 500
    return out


def scan_dutch():
    c = KalshiClient()
    events, cur, pg = [], None, 0
    while pg < 8:
        p = {"status": "open", "with_nested_markets": "true", "limit": 200}
        if cur:
            p["cursor"] = cur
        r = c._request("GET", "/events", params=p)
        events += r.get("events", [])
        cur = r.get("cursor")
        pg += 1
        if not cur:
            break

    def fee(pp):
        return 0.07 * pp * (1 - pp)

    hits = []
    for e in events:
        if not e.get("mutually_exclusive"):
            continue
        mks = e.get("markets", [])
        asks = [fnum(m.get("yes_ask_dollars")) for m in mks]
        bids = [fnum(m.get("yes_bid_dollars")) for m in mks]
        # require every outcome to be genuinely two-sided (real offer AND bid)
        if len(mks) < 2 or any(a is None or a >= 1.0 or a <= 0.0 for a in asks):
            continue
        if any(b is None or b <= 0.0 for b in bids):
            continue
        buy_edge = 1 - sum(asks) - sum(fee(a) for a in asks)
        sell_edge = sum(bids) - 1 - sum(fee(b) for b in bids)
        best = max(buy_edge, sell_edge)
        if best > 0:
            hits.append({"edge": round(best, 4), "buy_edge": round(buy_edge, 4),
                         "sell_edge": round(sell_edge, 4), "n": len(mks),
                         "event": e.get("event_ticker"), "title": e.get("title")})
    hits.sort(key=lambda x: -x["edge"])
    print(f"dutch-book: scanned {len(events)} events -> {len(hits)} positive-edge locks (net fees)")
    for h in hits[:20]:
        print(f"  edge={h['edge']:+.3f} n={h['n']} {h['event']} | {h['title'][:45]}")
    return hits


def scan_cross(sim_threshold=0.34):
    kal = pull_kalshi_markets()
    liq = [k for k in kal if k["ask"] and k["bid"] and k["ask"] < 1 and k["bid"] > 0]
    for k in liq:
        k["tok"] = toks(k["t"])
    poly = pull_polymarket()
    for p in poly:
        p["tok"] = toks(p["q"])
    print(f"kalshi liquid={len(liq)}  polymarket quoted={len(poly)}")

    real, rejected = [], []
    for k in liq:
        for p in poly:
            s = jac(k["tok"], p["tok"])
            if s < sim_threshold:
                continue
            e1 = p["bid"] - k["ask"]          # buy YES kalshi, hedge NO poly
            e2 = k["bid"] - p["ask"]          # buy YES poly, hedge NO kalshi
            lock = round(max(e1, e2) - 0.07 * 0.25, 4)   # rough kalshi-leg fee haircut
            ok, reason = is_equivalent(k["t"], p["q"])
            rec = {"sim": round(s, 2), "lock": lock, "reason": reason,
                   "kalshi": {"t": k["t"], "bid": k["bid"], "ask": k["ask"]},
                   "poly": {"q": p["q"], "bid": p["bid"], "ask": p["ask"]}}
            (real if ok else rejected).append(rec)

    real.sort(key=lambda x: -x["lock"])
    rejected.sort(key=lambda x: -x["lock"])
    print(f"\nEQUIVALENCE-CONFIRMED cross-venue pairs: {len(real)}")
    for r in real[:15]:
        print(f"  lock={r['lock']:+.3f} sim={r['sim']} K[{r['kalshi']['bid']:.2f}/{r['kalshi']['ask']:.2f}] "
              f"P[{r['poly']['bid']:.2f}/{r['poly']['ask']:.2f}]  {r['kalshi']['t'][:44]}")
    print(f"\nREJECTED as false matches (guard caught these): {len(rejected)} — top by fake 'edge':")
    for r in rejected[:8]:
        print(f"  FAKE lock={r['lock']:+.3f} ({r['reason']})")
        print(f"     K: {r['kalshi']['t'][:58]}")
        print(f"     P: {r['poly']['q'][:58]}")
    return {"real": real, "rejected": rejected}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["dutch", "cross"])
    args = ap.parse_args()
    result = scan_dutch() if args.mode == "dutch" else scan_cross()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"edge_scan_{args.mode}.json"
    with open(path, "w") as f:
        json.dump({"ts": time.time(), "mode": args.mode, "result": result}, f, indent=2)
    print(f"\nsaved -> {path}")


if __name__ == "__main__":
    main()
