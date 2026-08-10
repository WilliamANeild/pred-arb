"""Backtest metrics + the pre-registered go-live gate (docs/PLAN.md)."""
from __future__ import annotations

from dataclasses import dataclass

from .trade import BacktestTrade


@dataclass
class Metrics:
    n_trades: int
    total_pnl: float
    total_cost: float
    roc: float                 # return on capital-at-risk
    hit_rate: float
    sharpe: float              # per-trade
    max_drawdown: float        # dollars (<= 0)
    max_group_share: float     # largest single-group share of gross PnL


def compute_metrics(trades: list[BacktestTrade]) -> Metrics:
    n = len(trades)
    if n == 0:
        return Metrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    total_pnl = sum(t.pnl_usd for t in trades)
    total_cost = sum(t.cost_usd for t in trades)
    wins = sum(1 for t in trades if t.pnl_usd > 0)
    roc = total_pnl / total_cost if total_cost else 0.0
    hit = wins / n

    pnls = [t.pnl_usd for t in trades]
    mean = sum(pnls) / n
    var = sum((x - mean) ** 2 for x in pnls) / n
    std = var ** 0.5
    sharpe = mean / std if std > 0 else 0.0

    eq, peak, mdd = 0.0, 0.0, 0.0
    for x in pnls:
        eq += x
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)

    by_group: dict[str, float] = {}
    for t in trades:
        by_group[t.group_key] = by_group.get(t.group_key, 0.0) + t.pnl_usd
    gross = sum(abs(v) for v in by_group.values()) or 1.0
    max_share = max(abs(v) for v in by_group.values()) / gross

    return Metrics(n, total_pnl, total_cost, roc, hit, sharpe, mdd, max_share)


@dataclass
class GateVerdict:
    passed: bool
    reasons: list[str]


def go_live_gate(m: Metrics, *, min_trades: int = 30, max_group_share: float = 0.30,
                 min_hit: float = 0.60, max_dd_frac: float = 0.25) -> GateVerdict:
    """Pre-registered criteria. ALL must hold to consider real money."""
    reasons: list[str] = []
    dd_frac = abs(m.max_drawdown) / m.total_cost if m.total_cost else 1.0
    checks = {
        "positive net PnL & RoC after fees": m.total_pnl > 0 and m.roc > 0,
        f"enough samples (n>={min_trades})": m.n_trades >= min_trades,
        f"not concentrated (<= {max_group_share:.0%} in one group)": m.max_group_share <= max_group_share,
        f"acceptable hit rate (>= {min_hit:.0%})": m.hit_rate >= min_hit,
        "positive per-trade Sharpe": m.sharpe > 0,
        f"drawdown within {max_dd_frac:.0%} of capital": dd_frac <= max_dd_frac,
    }
    for name, ok in checks.items():
        if not ok:
            reasons.append(f"FAIL: {name}")
    return GateVerdict(passed=not reasons, reasons=reasons or ["all checks passed"])


def format_report(m: Metrics, gate: GateVerdict | None = None) -> str:
    lines = [
        f"  trades:            {m.n_trades}",
        f"  total PnL:         ${m.total_pnl:,.2f}",
        f"  capital at risk:   ${m.total_cost:,.2f}",
        f"  return on capital: {m.roc:+.1%}",
        f"  hit rate:          {m.hit_rate:.1%}",
        f"  per-trade Sharpe:  {m.sharpe:.2f}",
        f"  max drawdown:      ${m.max_drawdown:,.2f}",
        f"  max group share:   {m.max_group_share:.0%} of gross",
    ]
    if gate is not None:
        lines.append(f"  go-live gate:      {'PASS' if gate.passed else 'FAIL'}")
        lines += [f"    {r}" for r in gate.reasons]
    return "\n".join(lines)
