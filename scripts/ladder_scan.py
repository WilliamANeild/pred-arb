#!/usr/bin/env python3
"""Scan Kalshi ladders (player hits/HR, total runs) for monotonicity-violation
locks. Single-venue, riskless, no matching risk. Read-only.

  python scripts/ladder_scan.py
"""
import _bootstrap  # noqa: F401

from predarb.research.ladders import scan_ladders


def main():
    locks = scan_ladders()
    print(f"\n{len(locks)} ladder locks (monotonicity inversions, net of fees):\n")
    for lk in locks[:30]:
        print(f"  edge={lk.edge:+.3f}  buy YES>={lk.lo:g}@{lk.ask_lo:.2f} + NO>={lk.hi:g} "
              f"(bid {lk.bid_hi:.2f})")
        print(f"      {lk.ticker_lo}  |  {lk.ticker_hi}")
    if not locks:
        print("  none right now (ladders internally consistent).")


if __name__ == "__main__":
    main()
