"""Single-venue ladder-monotonicity arbitrage (Kalshi).

A "ladder" is a set of markets that are monotone thresholds of the SAME underlying:
a player's hits (1+, 2+, 3+), home runs (1+, 2+), or a game's total runs
(Over 5.5, 6.5, 7.5, ...). YES probability must be NON-INCREASING as the threshold
rises: P(>= t_hi) <= P(>= t_lo). When the live book violates that, there's a
RISKLESS lock — and it's single-venue, so there is zero cross-venue matching risk.

Lock: for thresholds t_lo < t_hi, buy YES(t_lo) and NO(t_hi).
  outcome >= t_hi -> $1 + $0 = $1
  t_lo <= outcome < t_hi -> $1 + $1 = $2
  outcome < t_lo -> $0 + $1 = $1
So payoff >= $1 always; cost = ask(t_lo) + (1 - bid(t_hi)). Lock iff
bid(t_hi) > ask(t_lo) (a price inversion), with edge = bid(t_hi) - ask(t_lo) - fees.
"""
from __future__ import annotations

import calendar
import re
import time
from dataclasses import dataclass

from ..common.logenv import get_logger
from ..venues.kalshi_client import KalshiClient

log = get_logger("research.ladders")

_MON = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def game_epoch(ticker: str) -> float | None:
    """UTC-ish epoch of the game from the ticker code (…-26AUG081915…). Treated as
    UTC for a coarse freshness window; a few hours of tz error is immaterial here."""
    m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})", ticker)
    if not m or m.group(2) not in _MON:
        return None
    yy, mon, dd = 2000 + int(m.group(1)), _MON[m.group(2)], int(m.group(3))
    hh, mm = int(m.group(4)), int(m.group(5))
    try:
        return calendar.timegm((yy, mon, dd, hh, mm, 0, 0, 0, 0))
    except (ValueError, OverflowError):
        return None


def _is_fresh(ticker: str, now: float, hours_back: float, days_fwd: float) -> bool:
    """Live or upcoming games only — excludes settled games with stale resting
    orders (the source of fake 'locks')."""
    ge = game_epoch(ticker)
    if ge is None:
        return False
    return (now - hours_back * 3600) <= ge <= (now + days_fwd * 86400)

LADDER_SERIES = ("KXMLBHIT", "KXMLBHR", "KXMLBTOTAL", "KXMLBF5TOTAL", "KXMLBTEAMTOTAL")


def _fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _fee(rate, p):
    p = max(0.0, min(1.0, p))
    return rate * p * (1.0 - p)


def _threshold(ticker: str, sub_title: str) -> float | None:
    """Player ladders encode the threshold in the ticker suffix (…-3); totals put it
    in the sub-title ("Over 8.5 runs scored")."""
    m = re.search(r"(\d+\.5)\b", sub_title or "")
    if m:
        return float(m.group(1))
    m = re.search(r"[:\s](\d+)\+?", sub_title or "")
    if m:
        return float(m.group(1))
    tail = ticker.rsplit("-", 1)[-1]
    return float(tail) if tail.isdigit() else None


def ladder_lock_edge(ask_lo: float, bid_hi: float, fee_rate: float = 0.07) -> float:
    """Net edge of buying YES(lower threshold) + NO(higher threshold). Positive only
    on a price inversion (bid of the higher, lower-probability rung exceeds the ask
    of the lower, higher-probability rung)."""
    return bid_hi - ask_lo - _fee(fee_rate, ask_lo) - _fee(fee_rate, 1.0 - bid_hi)


@dataclass
class LadderLock:
    group: str
    lo: float
    hi: float
    ask_lo: float
    bid_hi: float
    edge: float
    ticker_lo: str
    ticker_hi: str


def scan_ladders(series=LADDER_SERIES, fee_rate: float = 0.07, *,
                 fresh_only: bool = True, hours_back: float = 6.0,
                 days_fwd: float = 3.0) -> list[LadderLock]:
    c = KalshiClient()
    now = time.time()
    # group_key -> list of (threshold, ask, bid, ticker)
    groups: dict[str, list] = {}
    skipped_stale = 0
    for s in series:
        cur, pg = None, 0
        while pg < 10:
            p = {"series_ticker": s, "status": "open", "limit": 200}
            if cur:
                p["cursor"] = cur
            r = c._request("GET", "/markets", params=p)
            for m in r.get("markets", []):
                tk = m.get("ticker", "")
                if fresh_only and not _is_fresh(tk, now, hours_back, days_fwd):
                    skipped_stale += 1
                    continue
                ya, yb = _fnum(m.get("yes_ask_dollars")), _fnum(m.get("yes_bid_dollars"))
                if not (ya and yb and ya < 1 and yb > 0):
                    continue
                th = _threshold(tk, m.get("yes_sub_title", ""))
                if th is None:
                    continue
                gk = tk.rsplit("-", 1)[0]      # ticker without the threshold suffix
                groups.setdefault(gk, []).append((th, ya, yb, tk))
            cur = r.get("cursor")
            pg += 1
            if not cur:
                break

    locks: list[LadderLock] = []
    for gk, rungs in groups.items():
        if len(rungs) < 2:
            continue
        rungs.sort(key=lambda x: x[0])
        for i in range(len(rungs)):
            for j in range(i + 1, len(rungs)):
                th_lo, ask_lo, bid_lo, tk_lo = rungs[i]
                th_hi, ask_hi, bid_hi, tk_hi = rungs[j]
                if th_hi <= th_lo:
                    continue
                edge = ladder_lock_edge(ask_lo, bid_hi, fee_rate)
                if edge > 0:
                    locks.append(LadderLock(gk, th_lo, th_hi, ask_lo, bid_hi, edge, tk_lo, tk_hi))
    locks.sort(key=lambda x: -x.edge)
    log.info("scanned %d fresh ladder groups (%d stale markets skipped) -> %d locks",
             len(groups), skipped_stale, len(locks))
    return locks
