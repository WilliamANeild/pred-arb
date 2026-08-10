# pred-arb

Research-first arbitrage across prediction markets (Kalshi, Polymarket).

**Idea.** Group markets that resolve on the *same* underlying event, compute a
consensus probability across the group, and trade the members that deviate most:

- **Riskless dutch-book** — when cross-market prices are provably mispriced (buy
  the event's YES on one member and NO on another for a combined cost < \$1, or an
  under-priced mutually-exclusive outcome set), lock guaranteed profit.
- **Relative-value convergence** — when a member's price deviates from the group
  consensus by more than a threshold, bet on convergence. This carries **basis
  risk** (if the markets aren't truly identical the gap can be *correct*), so it is
  edge-gated, capped, and disabled for real money by default.

The whole point of the POC is that **matching mode** and **risk profile** are
pluggable strategies, and the backtester runs the full grid to tell us which
combination actually earns — rather than assuming.

## Status

**Proof of concept. Paper-only.** Real-money order placement is hard-disabled and
gated behind five independent switches (see `docs/SAFETY.md`). Do not enable live
trading until the backtest and a paper run both clear the go-live gate.

## Layout

```
src/predarb/
  common/    core types, config + safety flags, logging
  venues/    VenueAdapter ABC (capability model) · kalshi (signed) · polymarket (read)
             · odds (sportsbook lines, quote-only) · registry
  matching/  curated (YAML) · intra-event (partition) · cluster (NLP)  -> market groups
  signal/    consensus (mean/dispersion/deviation) · fees · risk profiles
  sizing/    confidence-weighted fractional-Kelly, capped
  backtest/  fill sim · metrics + go-live gate · replay harness · grid · synthetic data
  execute/   safety gate · paper broker · leg-risk executor (+ paper/live backends)
  engine/    live loop: snapshot all venues -> consensus -> leg-risk execution
  recorder/  snapshotter -> JSONL timeline (builds real backtest data over time)
scripts/     scan · record · backtest · paper_trade · live · preflight · panic
config/      params.yaml (strategy) · groups.yaml (curated equivalences)
```

**Venues** (see `docs/VENUES.md`): trade on what we can (Kalshi, Polymarket — order
books), read what we can't (sportsbook lines are quote-only and only inform
consensus). A **leg-risk executor** makes multi-leg cross-venue locks safe to
attempt: thinnest leg first, abort on price drift, auto-unwind if a leg fails.

## Quickstart

```bash
poetry install
cp .env.example .env          # fill in keys later; reads work without them

# 1. Prove the plumbing end-to-end on synthetic data (no network, no keys):
poetry run python scripts/backtest.py --synth        # runs the full matcher x profile grid

# 2. Safety self-check (must pass before any real run):
poetry run python scripts/preflight.py

# 3. Read-only live opportunity scan (needs network; no keys required for reads):
poetry run python scripts/scan.py

# 4. Start recording real market snapshots to build a backtest dataset:
poetry run python scripts/record.py --minutes 60

# Emergency stop at any time:
poetry run python scripts/panic.py
```

## Docs

- `docs/PLAN.md` — phased roadmap and the pre-registered go-live gate.
- `docs/STRATEGY.md` — the math: consensus, locks, relative value, sizing.
- `docs/SAFETY.md` — every safeguard and the real-money runbook.

The Kalshi client (RSA-PSS request signing, post-2026 fixed-point orderbook
handling) is lifted from a prior project of the author's.
