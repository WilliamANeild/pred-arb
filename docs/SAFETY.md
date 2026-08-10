# Safety — real-money runbook

Safeguards are the point of this project. Real orders are **off** by default and
require **five independent** conditions to all be true.

## The five gates (all required for a real order)

1. `ALLOW_LIVE_TRADING=true` in `.env` (global opt-in).
2. `KALSHI_ENV=prod` (demo can never place real Kalshi money).
3. The per-run `--live` flag on the command.
4. Interactive confirmation at runtime (type the confirmation phrase).
5. Every risk cap and strategy guard below passes for the specific order.

Miss any one → the order is simulated by the paper broker instead. This is
enforced in `execute/safety.py:SafetyGate` and `common/config.py:SafetyConfig`.

## Kill switch (instant stop)

- `python scripts/panic.py` writes `data/KILL`.
- Any existing `data/KILL` file, or `KILL_SWITCH=true`, blocks **all** order
  placement (paper and live) immediately, checked before every order.
- `python scripts/panic.py --clear` removes it.

## Risk caps (env-configurable, tiny defaults)

| Cap                            | Env var                        | Default |
|--------------------------------|--------------------------------|---------|
| Max contracts / order          | `MAX_CONTRACTS_PER_ORDER`      | 20      |
| Max \$ / market                | `MAX_NOTIONAL_PER_MARKET_USD`  | 25      |
| Max \$ / arb group (all legs)  | `MAX_NOTIONAL_PER_GROUP_USD`   | 40      |
| Max \$ total / run             | `MAX_TOTAL_NOTIONAL_USD`       | 100     |
| Daily realized-loss stop       | `DAILY_LOSS_LIMIT_USD`         | 50      |
| Max price paid / contract      | `MAX_PRICE_CENTS`              | 97      |
| Max orders / session           | `MAX_ORDERS_PER_SESSION`       | 25      |

## Circuit breakers

- **Consecutive errors** (`MAX_CONSECUTIVE_ERRORS`, default 3): auto-engage the kill
  switch after this many order errors in a row.
- **Feed staleness** (`FEED_STALENESS_SECONDS`, default 120): never act on a market
  snapshot older than this.

## Strategy guards (arb-specific)

- `LIVE_RISKLESS_ONLY=true` (default): real money only on riskless dutch-book locks;
  relative-value / basis-risk trades are paper-only until deliberately relaxed.
- `MIN_EDGE_LIVE` (default 0.03): fee-adjusted edge floor for a real order.
- Medium band `MIN_CONSENSUS`/`MAX_CONSENSUS` (0.15–0.85): no longshot tails.
- `MIN_DEPTH_CONTRACTS` / `MAX_SPREAD`: skip illiquid or wide books.
- `CLUSTER_TRUST_FLOOR` (0.80): a cluster-(NLP)-matched group may not place real
  money unless its similarity clears this floor (and even then, sized smallest).

## Before any live session

```bash
poetry run python scripts/preflight.py   # verifies caps, keys, kill file, clock
```

Preflight refuses to green-light live trading unless every gate above is coherent.
