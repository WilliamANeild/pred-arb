# Strategy

## 1. Grouping (the whole game)

Everything downstream is only as sound as the assertion that a set of markets
resolves on the *same* event. We support three **matchers**, each with a `trust`
weight that later dampens real-money sizing:

| Matcher      | How it groups                                             | Trust | Risk if wrong                          |
|--------------|----------------------------------------------------------|-------|----------------------------------------|
| `curated`    | Hand-written `config/groups.yaml`                        | 1.0   | You asserted it — verify carefully     |
| `intraevent` | Mutually-exclusive outcomes inside one Kalshi event      | 1.0   | Structural; near-zero                   |
| `cluster`    | NLP title similarity across events                       | ~sim  | **High** — false matches = hidden risk |

A group is one of two `kind`s:

- **equivalence** — every member resolves identically to a binary event `E`.
  Each member `i` has a **polarity** `s_i ∈ {+1, -1}`: whether member-YES means
  `E=yes` (+1) or `E=no` (-1, an inverse-worded market).
- **partition** — members are the mutually-exclusive, collectively-exhaustive
  outcomes of one event; their YES probabilities should sum to ~1.

## 2. Consensus

For an equivalence group, convert each member's mid price to an implied
`P(E=yes)`:

```
p_i = mid_i        if s_i = +1
p_i = 1 - mid_i    if s_i = -1
```

Consensus `p*` is the (optionally liquidity-weighted) mean of `p_i`. **Dispersion**
is `max_i p_i − min_i p_i`. A member's **deviation** is `p_i − p*`.

Only groups whose `p*` sits in the **medium band** `[MIN_CONSENSUS, MAX_CONSENSUS]`
(default 0.15–0.85) are eligible — the 1–10% longshot tails are where one surprise
wipes the whole book, which is the drawdown you specifically wanted to avoid.

## 3. Opportunities

### Riskless dutch-book (no basis risk beyond a wrong grouping)

- **Equivalence pair lock.** For members A, B on event `E`, buy `E=yes` via A and
  `E=no` via B. Cost = `ask^E_yes(A) + ask^E_no(B)` (fee-adjusted). If `< 1`, the
  \$1 settlement is guaranteed regardless of outcome → edge `= 1 − cost`.
- **Partition under-round.** For a partition, if `Σ ask_yes(outcome) < 1`, buy every
  outcome's YES: exactly one pays \$1 → edge `= 1 − Σ ask`. (The mirror, `Σ bid > 1`,
  is a sell-all lock; enabled once short/So-side execution is wired.)

### Relative-value convergence (has basis risk — gated + capped)

Take the member with the largest `|deviation|`. If it *under-prices* `E=yes`
(`p_i ≪ p*`), buy `E=yes` via that member at its ask; expected edge is
`p* − entry` minus fees. Exit when the gap narrows to `close_deviation` or at
settlement. This is a bet that the outlier converges to the crowd — **profitable
only if the grouping is right and the crowd is.**

## 4. Risk profiles (backtested against each other)

| Profile          | Emits                                   |
|------------------|-----------------------------------------|
| `riskless_only`  | dutch-book locks only                   |
| `relative_value` | convergence trades only                 |
| `both`           | locks preferred, plus gated convergence |

The grid backtest (`scripts/backtest.py`) runs every `matcher × profile` and ranks
them by the pre-registered metrics in `docs/PLAN.md`.

## 5. Sizing (confidence-weighted)

Real money is sized *per trade by confidence*, as you asked:

```
confidence = f(edge magnitude, group agreement, liquidity) × matcher_trust
size       = fractional_Kelly(edge, price) × confidence × bankroll
             capped by per-order / per-market / per-group / total notional limits
```

Dutch-book locks get confidence ≈ 1 (the profit is structural). Relative-value
confidence scales with how far the outlier sits from a *tight* consensus and how
deep the book is, and is dampened by the matcher's trust (cluster groups get the
smallest size). Below `confidence_floor`, size is 0.

## 6. Fees

Kalshi taker fee `= ceil(rate · n · p · (1−p) · 100) / 100` per fill; Polymarket
≈ 0. Every edge above is computed **after** fees — a lock that's only profitable
pre-fee is not a lock.
