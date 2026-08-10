# Running list — what I need from you

Kept up to date as we go. Nothing here blocks read-only research; these unlock the
next stages.

## Decisions
- [ ] **Pursue live/in-play latency arb?** The research says that's where the only
      real edge likely is — but it means aggressive taking against stale quotes,
      which is the behavior that risks Kalshi/Polymarket bans. Do we (a) pursue it
      carefully/passively, (b) stay riskless-only and accept "probably no edge", or
      (c) pivot the thesis? **Your call — this steers everything.**
- [ ] Risk appetite for basis (relative-value) trades vs riskless-only.
- [ ] Which sports/topics to focus the live recorder on first (MLB? tennis? NFL
      once season starts? politics/crypto?).

## Access / keys (only needed to TRADE, not to research)
- [ ] **Kalshi prod API key** (RSA key pair from Kalshi → Profile → API Keys) — to
      place real Kalshi orders. Put the PEM at `secrets/` and IDs in `.env`.
- [ ] **Polymarket**: funded USDC wallet on Polygon + L2 API key — to place there.
      Bigger lift; only when we're ready to trade cross-venue.
- [ ] **the-odds-api key** (optional, free tier) — to pull sportsbook lines as a
      sharp consensus input. Set `ODDS_API_KEY` / `ODDS_API_ENABLED=true`.

## Confirmations
- [ ] For any curated pair we might trade: confirm the two markets truly resolve
      identically (same date, same source, close-vs-touch) — I'll draft, you verify.
- [ ] Confirm you want the repo to stay **private** (it is).

## Nothing needed for
- Recording public market data, backtesting, building the WebSocket layer, the
  paper engine — I can proceed on all of these now.
