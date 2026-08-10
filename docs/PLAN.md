# Plan & pre-registered go-live gate

## Phases

**Phase 0 — POC (this commit).** Full pipeline, paper-only:
- Venue adapters (Kalshi signed client lifted from prior project; Polymarket read-only).
- Three matchers (curated / intra-event / cluster) → market groups.
- Consensus + risk profiles (riskless / relative-value / both).
- Confidence-weighted sizing with hard caps.
- Backtest harness + **grid** over every matcher × profile, on synthetic data now
  and recorded data as it accumulates.
- Safety gate, paper broker, hard-gated live executor.
- Recorder to snapshot real markets into a backtest dataset.
- Tests for every safety-critical path.

**Phase 1 — Data + selection.** Run `scripts/record.py` for a sustained window to
build a real snapshot timeline; run the grid; pick the matcher × profile that clears
the go-live gate with the best risk-adjusted return. Freeze `config/params.yaml`.

**Phase 2 — Paper-live.** Run the chosen config against the live feed through the
**paper broker** for a paper track record. No real money.

**Phase 3 — Tiny real money.** Only after Phases 1–2 pass the gate. Start with
`riskless_only` and single-digit-dollar caps; size by confidence; scale slowly.

## Pre-registered go-live gate

Freeze these BEFORE reporting a backtest so results aren't hindsight-tuned. **All**
must hold, on out-of-sample recorded data, to consider real money:

1. Positive net PnL and return-on-capital **after fees**.
2. `n_trades ≥ 30` (enough samples).
3. No single group is `> 30%` of gross PnL (not one lucky event).
4. Positive per-trade Sharpe.
5. Max drawdown `≤ 25%` of deployed capital.
6. For any profile that includes relative-value: the **riskless-only** slice of the
   same run must itself be non-negative (we are not subsidizing basis-risk bets with
   lock profits).

`backtest/metrics.py:go_live_gate()` enforces 1–5 mechanically; 6 is checked by the
grid comparison in `backtest/grid.py`.

## Open questions to resolve with real data

- Which matcher yields the best trust-adjusted edge? (Hypothesis from the author:
  intra-event.)
- Does relative-value add anything over riskless-only once basis losses are counted?
- Real Polymarket↔Kalshi settlement-timing and currency (USDC) frictions on locks.
