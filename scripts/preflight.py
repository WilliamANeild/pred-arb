#!/usr/bin/env python3
"""Safety self-check. Prints the current state of every gate and refuses to
green-light live trading unless the whole configuration is coherent.

  python scripts/preflight.py
"""
import _bootstrap  # noqa: F401

from predarb.common.config import KalshiConfig, PolymarketConfig, SafetyConfig


def main():
    s = SafetyConfig()
    k = KalshiConfig()
    p = PolymarketConfig()

    print("=== pred-arb preflight ===\n")
    print(f"kalshi env:            {k.env}")
    print(f"kalshi credentials:    {'present' if k.has_credentials() else 'MISSING (reads only)'}")
    print(f"polymarket:            {'enabled (read-only)' if p.enabled else 'disabled'}\n")

    print("--- live-trading gates ---")
    print(f"ALLOW_LIVE_TRADING:    {s.allow_live_trading}")
    print(f"KALSHI_ENV == prod:    {k.is_prod}")
    print(f"kill switch engaged:   {s.kill_engaged()}   (file: {s.kill_file})")
    print(f"live riskless-only:    {s.live_riskless_only}")
    print(f"min edge (live):       {s.min_edge_live}")

    print("\n--- risk caps ---")
    print(f"bankroll:              ${s.bankroll_usd}")
    print(f"max contracts/order:   {s.max_contracts_per_order}")
    print(f"max $/market:          ${s.max_notional_per_market_usd}")
    print(f"max $/group:           ${s.max_notional_per_group_usd}")
    print(f"max $ total:           ${s.max_total_notional_usd}")
    print(f"daily loss limit:      ${s.daily_loss_limit_usd}")
    print(f"consensus band:        [{s.min_consensus}, {s.max_consensus}]")

    would_live = s.live_allowed(k.env, run_live_flag=True)
    print("\n--- verdict ---")
    if would_live and k.has_credentials():
        print("LIVE-CAPABLE: a run with --live COULD place real orders. Caps still apply.")
    else:
        blockers = []
        if not s.allow_live_trading:
            blockers.append("ALLOW_LIVE_TRADING=false")
        if not k.is_prod:
            blockers.append("KALSHI_ENV != prod")
        if s.kill_engaged():
            blockers.append("kill switch engaged")
        if not k.has_credentials():
            blockers.append("no Kalshi credentials")
        print("PAPER-ONLY (safe). Blockers: " + ", ".join(blockers))


if __name__ == "__main__":
    main()
