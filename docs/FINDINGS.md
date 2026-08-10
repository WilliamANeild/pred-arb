# Findings — live edge research (2026-08-10)

First real-data pass against live Kalshi + Polymarket. All read-only.

## What we measured

- Pulled **10,000** open Kalshi markets; only **~845 (≈8%) are two-sided liquid**
  (real bid AND ask). Most Kalshi markets are one-sided/illiquid.
- Pulled **~420** liquid-quoted Polymarket markets (Gamma `bestBid/bestAsk`).
- Scanned **206 mutually-exclusive Kalshi events** for single-venue dutch books.
- Cross-matched the liquid sets by title, then applied a structured equivalence
  guard (`signal/equivalence.py`).

## Result 1 — single-venue Kalshi dutch books: real but not tradeable

Positive-edge under-round locks exist, but they are:
- **Tiny**: best genuine ones ≈ **+1.7%** (e.g. 2028 Senate two-party markets,
  Σask≈0.98), a few at +0.8%.
- **Long-dated**: mostly 2028 elections → capital locked ~2 years for ~2% ⇒ ~1%/yr.
- Everything that looked bigger was a data artifact (markets with **no offer**, i.e.
  `yes_ask=0`, which you can't actually buy — the scanner now filters these out).

**Verdict:** heavily bot-arbed, no meaningful edge after capital-lock and fees.

## Result 2 — cross-venue "locks": every big one is a FALSE match

The naive title-matcher's most attractive "edges" were all matching errors:

| Fake "edge" | Reality |
|---|---|
| +0.63 Bitcoin $70k | Kalshi **Aug-10 daily close** vs Polymarket **by Dec 31** — different date |
| +0.53 Bitcoin $62k | "above" vs "**dip to**" — opposite polarity |
| +0.18…+0.48 "Milwaukee O/U" ladder | Kalshi **Over 1.5/2.5/…** vs Polymarket **O/U 7.5** — different line |
| +0.18 Alvarez HR | **this game** vs **most HR all season** — different event |

The structured guard (threshold + direction + date) rejected **19/22** candidates.

**But even the 3 survivors aren't arbitrage.** `Bitcoin $70k or above` prices at
**2% on Kalshi** (daily close, Aug 10) vs **21% on Polymarket** (touch-anytime in a
range). Same number, different *resolution semantics* → a touch is far likelier than
a close-above. The gap is real basis, not free money.

**Verdict:** on static REST data, genuinely-identical contracts are efficiently
priced (~0 edge); every large gap decomposes into date / close-vs-touch / timeframe
/ polarity differences. A title-similarity matcher doesn't find edge — it finds
traps. (This is exactly the project's founding premise: matching correctness *is*
the risk.)

## Implication — where the edge actually is

Your source said "there's an edge but they ban you." That is consistent with
**live / in-play latency**, not static mispricing:

- During a live event, the two venues re-price at **different speeds** with
  different crowds; a real (same-contract) dislocation can open for seconds.
- Capturing it means **aggressive taking against a stale quote** — which is fast,
  small-window, and precisely the behavior that draws ToS/ban attention.
- A periodic REST scan (what we have) **cannot see or capture** these; it needs
  tick-level WebSocket data and fast, leg-risk-bounded execution.

So the next real experiment is: **stream a semantically-verified, identical live
pair tick-by-tick and measure whether dislocations (a) occur, (b) exceed fees, and
(c) persist long enough to fill both legs.** If they don't, there is no capturable
edge and we should not risk money; if they do, we size tiny and passively.

## What did NOT show an edge (so we stop chasing it)

- Static cross-venue riskless locks on identical contracts.
- Single-venue dutch books at tradeable size / sane duration.

## Next steps (ranked)

1. **WebSocket streaming layer** (Kalshi + Polymarket) + tick recorder — the only
   way to test the live-latency thesis.
2. **Curated, semantics-verified pairs** — hand-pick a handful of truly-identical
   live markets (needs human confirmation of resolution rules), record those.
3. Backtest the recorded ticks for dislocation frequency/size/persistence before
   any capital.

## Update — live streaming layer built & validated (MLB)

Built and tested end-to-end against live data:
- **Polymarket WebSocket** (public, no auth) — `price_change` carries
  `best_bid`/`best_ask` per token; feeds a live top-of-book cache tick-by-tick.
- **Kalshi fast REST poller** (public, no key; Kalshi WS needs auth) — swappable for
  a Kalshi WS client later.
- **Tick recorder** → `data/ticks/<session>.jsonl`; **dislocation analyzer**
  measures frequency / size / **persistence** (the make-or-break metric).
- **MLB pair matcher** — moneyline + totals, matched on teams **and game date**.

Two correctness lessons from real data:
- Same-team, **different-date** games are different games. Polymarket has no date in
  the title; must match on `gameStartTime` vs the Kalshi ticker's date code. (A naive
  team-only match paired a Polymarket Aug-10 game with Kalshi Aug-12/13 games — 3 days
  off — which would manufacture fake dislocations.) **Fixed** (exact-day match).
- Open TZ caveat: Kalshi ticker time-zone vs Polymarket UTC can shift late-night games
  by a day; exact-day match may miss those. Refine with real tz normalization.

**To actually get the measurement:** run `scripts/mlb_pairs.py` then
`scripts/stream_record.py` **during a live MLB game** (in-play, prices moving), then
`scripts/analyze_dislocation.py`. Pre-game markets are quiet; the thesis is about
*in-play* latency, so the recording must span first-pitch onward.

## Update — every-line coverage + first live recording

- **Cross-venue overlap is narrow.** Of all MLB line types, only **moneyline** and
  **total runs** are liquid on *both* venues. Polymarket doesn't carry Kalshi's F5,
  run-line, team-total, or player-prop ladders as tradeable pairs — so there are no
  cross-venue pairs for those.
- **Single-venue Kalshi ladders** (player hits/HR, total-runs Over ladders) *must*
  be monotonic; inversions are riskless locks. Scanned live: the only "locks" were on
  **settled games** (stale resting orders) — filtered out by a game-freshness guard
  (4,759 stale markets skipped). Among **60 fresh ladder groups: 0 locks** → live
  ladders are internally consistent (efficient).
- **First live recording** across 3 in-play MLB games (moneyline pairs). The
  end-to-end pipeline (WS + poll → cache → tick log → dislocation analysis) is
  validated on real data. Preliminary (partial) read: **no capturable dislocation**
  — but the sample is tiny; the full in-play window is the real test.

**Running theme confirmed again:** fresh, liquid markets are efficient; the apparent
edges are artifacts (settled-game stale orders, false matches, resolution-semantics
gaps). Any real edge is a fleeting in-play latency event — which the recorder now
captures for measurement before any capital is risked.
