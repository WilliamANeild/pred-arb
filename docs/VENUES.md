# Venues

Goal: **trade on everything we actually can, and read everything else to sharpen
the signal.** Each adapter declares a capability, and the engine treats it
accordingly.

| Venue | `market_type` | `executable` | In POC | Notes |
|-------|---------------|--------------|--------|-------|
| **Kalshi** | orderbook | yes (with prod key) | read + trade | RSA-PSS signed client. Reads public; trading needs a prod API key. |
| **Polymarket** | orderbook | no (POC) | read only | Reads public (Gamma+CLOB). Trading needs a funded USDC/Polygon wallet + L2 key. |
| **Sportsbooks** (the-odds-api) | fixed_odds | no | read only | DraftKings/FanDuel/Pinnacle lines. No bet API — **quote-only**. |
| **Betfair** (future) | exchange | yes (geo-limited) | not yet | A real exchange with an API; add when needed. |

## Capability rules

- **`market_type = "orderbook"`** — has depth, can be a trade leg (Kalshi, Polymarket).
- **`market_type = "fixed_odds"`** — a single de-vigged probability, **no depth**.
  Its snapshot carries empty ladders, so the signal layer can use it for consensus
  but can never form a fillable leg from it. `quote_only` is `True`.
- **`executable`** — whether orders can be placed via API at all. The live path only
  routes to venues where `supports_trading()` (executable **and** authenticated).

So sportsbook lines pull the consensus toward the sharp price (Pinnacle especially),
which makes a Kalshi/Polymarket outlier easier to spot — but we only ever *place* on
the order-book venues.

## Live data

REST polling (current recorder/engine) is fine for validation but too slow for
in-play capture. WebSocket feeds exist for both order-book venues and are the next
step:

- Kalshi WS: `wss://…/trade-api/ws/v2` (orderbook_delta, ticker, trades, fills).
- Polymarket WS: `wss://ws-subscriptions-clob.polymarket.com/ws/market`.

`common/config.py` already holds these URLs; the streaming clients plug into the
same normalized `Book` the REST adapters produce, so nothing downstream changes.

## Leg risk (why live cross-venue is the dangerous part)

A cross-venue lock is **not atomic**. `execute/legrisk.py` bounds the exposure:
fill the thinnest leg first, abort if any leg fills worse than `max_leg_drift`, and
unwind every filled leg the instant a later leg fails. The safest live product is a
**single-venue** intra-event dutch book (one order book → effectively no leg risk),
which is also where a lot of live mispricing shows up.
