"""Dislocation analysis — the core measurement.

Replays recorded ticks for a cross-venue Pair, reconstructs both venues'
top-of-book over time, and at each tick computes the fee-adjusted cross-venue
lock edge. Then it reports the three things that decide whether the live edge is
real and *capturable*:

  1. frequency  — how often a positive-edge lock exists,
  2. size       — how big (does it clear fees?),
  3. persistence— how long each dislocation stays open (can you fill both legs?).

Persistence is the make-or-break number: a lock that exists for 200ms and vanishes
is not tradeable; one that persists for seconds might be.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .pairs import Pair


def _fee(rate: float, price: float) -> float:
    p = max(0.0, min(1.0, price))
    return rate * p * (1.0 - p)


def _tradeable(bid, ask, *, min_p=0.03, max_p=0.97, max_spread=0.12) -> bool:
    """A genuinely two-sided, non-degenerate book. Filters out the illiquid /
    one-sided quotes (0/0, 0.02/0.98, x/0) that manufacture fake locks."""
    if bid is None or ask is None:
        return False
    if not (min_p <= bid < ask <= max_p):
        return False
    return (ask - bid) <= max_spread


@dataclass
class DislocationStats:
    pair_label: str
    n_ticks: int = 0
    n_both: int = 0                 # ticks where both venues had a top-of-book
    frac_dislocated: float = 0.0    # share of both-known ticks with a positive lock
    max_lock: float = 0.0
    mean_positive_lock: float = 0.0
    n_episodes: int = 0
    median_episode_s: float = 0.0
    max_episode_s: float = 0.0
    total_dislocated_s: float = 0.0   # summed episode duration (duration-weighted)
    duration_s: float = 0.0
    series: list = field(default_factory=list)   # (ts, lock) — optional, for plots


def load_ticks(path: str | Path) -> list[dict]:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _poly_event_terms(bid, ask, polarity):
    """Return (event_yes_bid, event_yes_ask) for the polymarket leg."""
    if polarity == 1:
        return bid, ask
    # inverse-worded: event-YES via polymarket = buy NO; bid/ask reflect.
    eb = None if ask is None else 1.0 - ask
    ea = None if bid is None else 1.0 - bid
    return eb, ea


def analyze(ticks: list[dict], pair: Pair, mode: str = "taker") -> DislocationStats:
    """mode="taker": cross both spreads, pay Kalshi fee (what we measured first).
    mode="maker": REST limit orders (buy at bid / sell at ask), earn the spread and
    pay no taker fee. The maker lock is ~one full spread wider and fee-free — but it
    ASSUMES both resting legs fill, which a backtest cannot guarantee (fill depends on
    counterparty flow). Treat maker numbers as an UPPER BOUND to confirm live."""
    st = DislocationStats(pair_label=f"{pair.label} [{mode}]", n_ticks=len(ticks))
    kbid = kask = pbid = pask = None
    series = []
    kkey, pkey = pair.kalshi_ticker, pair.poly_token

    ts_first = ts_last = None
    for t in sorted(ticks, key=lambda r: r["ts"]):
        if t["venue"] == "kalshi" and t["market_id"] == kkey:
            kbid, kask = t["yes_bid"], t["yes_ask"]
        elif t["venue"] == "polymarket" and t["market_id"] == pkey:
            pbid, pask = _poly_event_terms(t["yes_bid"], t["yes_ask"], pair.polarity)
        else:
            continue
        ts = t["ts"]
        ts_first = ts if ts_first is None else ts_first
        ts_last = ts
        # both venues must show a genuine two-sided book, or the "lock" is a phantom.
        if not (_tradeable(kbid, kask) and _tradeable(pbid, pask)):
            continue
        if mode == "maker":
            # rest buy-YES @ bid on the cheap venue + buy-NO @ (1 - ask) on the dear
            # venue; earn the spread, no taker fee.
            lock = max(kask - pbid, pask - kbid)
        else:
            # taker: cross both spreads and pay the Kalshi taker fee.
            lock1 = pbid - kask - _fee(pair.fee_rate, kask)
            lock2 = kbid - pask - _fee(pair.fee_rate, 1.0 - kbid)
            lock = max(lock1, lock2)
        series.append((ts, lock))

    st.n_both = len(series)
    st.duration_s = (ts_last - ts_first) if (ts_first and ts_last) else 0.0
    if not series:
        return st

    pos = [(ts, lk) for ts, lk in series if lk > 0]
    st.frac_dislocated = len(pos) / len(series)
    if pos:
        st.max_lock = max(lk for _, lk in pos)
        st.mean_positive_lock = sum(lk for _, lk in pos) / len(pos)

    # episodes: maximal runs of consecutive positive-lock ticks
    episodes = []
    run_start = None
    prev_ts = None
    for ts, lk in series:
        if lk > 0:
            if run_start is None:
                run_start = ts
            prev_ts = ts
        else:
            if run_start is not None:
                episodes.append(prev_ts - run_start)
                run_start = None
    if run_start is not None:
        episodes.append(prev_ts - run_start)

    st.n_episodes = len(episodes)
    if episodes:
        ordered = sorted(episodes)
        st.median_episode_s = ordered[len(ordered) // 2]
        st.max_episode_s = ordered[-1]
        st.total_dislocated_s = sum(episodes)
    st.series = series
    return st


def _verdict(st: DislocationStats) -> str:
    if not st.n_episodes or st.max_lock <= 0:
        return "VERDICT: no positive-edge dislocation observed"
    persistent = st.max_episode_s >= 1.0
    if "[maker]" in st.pair_label:
        # The maker "lock" is essentially the combined cross-venue spread — an UPPER
        # BOUND that ignores fill probability and adverse selection (you get filled on
        # the leg about to move against you). Neither is measurable from top-of-book
        # data, so this can only be confirmed by a small LIVE test.
        return (f"VERDICT: maker upper-bound {st.mean_positive_lock:+.1%} mean "
                f"({st.frac_dislocated:.0%} of ticks) — GROSS spread before fill "
                f"probability & adverse selection; NOT backtestable, needs a tiny live test")
    # taker
    tradeable_edge = st.max_lock >= 0.03
    if persistent and tradeable_edge:
        return ("VERDICT: persistent AND sizeable -> candidate edge; CONFIRM with "
                "real-time Kalshi WS (REST polling may show stale-quote locks)")
    if persistent:
        return (f"VERDICT: persistent (up to {st.max_episode_s:.0f}s) but tiny "
                f"(max {st.max_lock:+.1%}) -> fees/slippage likely eat it; not worth taker execution")
    return "VERDICT: only sub-second flickers -> not capturable by taking"


def format_stats(st: DislocationStats) -> str:
    return "\n".join([
        f"=== {st.pair_label} ===",
        f"  ticks:               {st.n_ticks}  (both-venue: {st.n_both})",
        f"  window:              {st.duration_s:.0f}s",
        f"  dislocated fraction: {st.frac_dislocated:.1%}",
        f"  max lock edge:       {st.max_lock:+.3f}",
        f"  mean positive lock:  {st.mean_positive_lock:+.3f}",
        f"  episodes:            {st.n_episodes}  (total {st.total_dislocated_s:.0f}s dislocated)",
        f"  median / max episode:{st.median_episode_s:.2f}s / {st.max_episode_s:.2f}s",
        f"  {_verdict(st)}",
    ])
