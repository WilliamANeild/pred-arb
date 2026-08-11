# Running list — what I need from you

Kept up to date as we go. Nothing here blocks read-only research; these unlock the
next stages.

## Decisions
- [x] **Pursue live/in-play latency arb?** → YES, carefully. Measure first (no
      trading) via the streaming/recorder layer. (2026-08-10)
- [x] Focus venue/sport first → **MLB** (2026-08-10).
- [ ] **Run a recording during a live MLB game?** The measurement needs in-play data
      (first pitch onward). Do you want to run `scripts/stream_record.py` yourself
      during a game tonight, or should I set up a background/scheduled recording for
      a specific game window? (Games are ~7pm ET; tell me which and I'll wire it.)
- [ ] Risk appetite for basis (relative-value) trades vs riskless-only.

## Known refinements (I can do these; flagging for visibility)
- [ ] **Same-day Kalshi game coverage** — the generic Kalshi feed didn't surface
      *today's* MLB games in my pull; discovery should query the KXMLBGAME series
      directly at game time. (Matcher logic is correct; this is data coverage.)
- [ ] **Timezone normalization** for game-date matching (Kalshi ticker tz vs
      Polymarket UTC) so late-night games aren't dropped.

## Access / keys
- [ ] **Kalshi DEMO API key** (free — Kalshi → Profile → API Keys, demo env) — NOW
      the concrete blocker. Needed to enable Kalshi **WebSocket** (real-time), which
      removes the REST-polling confound and gives a clean in-play measurement. No
      money involved; demo keys can't trade real funds. Put the PEM in `secrets/` and
      set `KALSHI_KEY_ID` in `.env`.
- [ ] **Kalshi prod API key** (later, to place real orders once an edge is proven).
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
