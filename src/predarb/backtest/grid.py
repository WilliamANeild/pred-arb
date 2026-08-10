"""Grid backtest — run every matcher x profile combination over one timeline and
rank them. This is the experiment the whole POC exists to run: it tells us which
matching mode and which risk profile actually earn, rather than assuming.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..common.config import SafetyConfig
from ..common.types import MarketGroup, MarketRef
from ..matching import build_matcher
from ..signal.profiles import build_profile
from .harness import backtest_metrics
from .metrics import Metrics, go_live_gate


@dataclass
class GridCell:
    matcher: str
    profile: str
    n_groups: int
    metrics: Metrics
    gate_passed: bool
    gate_reasons: list[str]


def run_grid(frames, refs: list[MarketRef], params: dict, safety: SafetyConfig, *,
             matchers=("curated", "intraevent", "cluster"),
             profiles=("riskless_only", "relative_value", "both"),
             curated_groups: list[MarketGroup] | None = None,
             min_trades: int = 30) -> list[GridCell]:
    cells: list[GridCell] = []
    for mname in matchers:
        if mname == "curated" and curated_groups is not None:
            groups = curated_groups
        else:
            groups = build_matcher(mname).build(refs)
        for pname in profiles:
            profile = build_profile(pname)
            _, m = backtest_metrics(frames, groups, profile, params, safety, mname)
            gate = go_live_gate(m, min_trades=min_trades)
            cells.append(GridCell(matcher=mname, profile=pname, n_groups=len(groups),
                                  metrics=m, gate_passed=gate.passed,
                                  gate_reasons=gate.reasons))
    # rank: passing gate first, then RoC, then Sharpe
    cells.sort(key=lambda c: (c.gate_passed, c.metrics.roc, c.metrics.sharpe), reverse=True)
    return cells


def format_grid(cells: list[GridCell]) -> str:
    hdr = f"{'matcher':<12} {'profile':<15} {'grps':>4} {'trades':>6} {'PnL$':>9} {'RoC':>7} {'hit':>6} {'Sharpe':>7} {'maxDD$':>8} {'gate':>5}"
    lines = [hdr, "-" * len(hdr)]
    for c in cells:
        m = c.metrics
        lines.append(
            f"{c.matcher:<12} {c.profile:<15} {c.n_groups:>4} {m.n_trades:>6} "
            f"{m.total_pnl:>9.2f} {m.roc:>6.1%} {m.hit_rate:>5.0%} {m.sharpe:>7.2f} "
            f"{m.max_drawdown:>8.2f} {'PASS' if c.gate_passed else 'fail':>5}"
        )
    return "\n".join(lines)
