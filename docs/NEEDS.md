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

## Access / keys — for the tiny live maker test (decided: prod-small, not demo)
The maker edge can't be backtested (fill probability + adverse selection aren't in
public data), so validating it needs a small live test on BOTH venues.

- [ ] **Kalshi PROD API key** (Profile → API Keys, prod). Caps stay tiny in `.env`
      (single-digit $ per market). PEM in `secrets/`, `KALSHI_KEY_ID` in `.env`,
      `KALSHI_ENV=prod`. Also unlocks the real-time Kalshi WebSocket (cleaner data).
- [x] **Which Polymarket?** → **Polymarket US (QCX)** — the CFTC-regulated, US-legal
      venue, same footing as Kalshi. (2026-08-12) NOT international (geo-blocked).
- [ ] **Polymarket US onboarding (THE current blocker — even reads need it).** Auth is
      RSA Private-Key-JWT, like Kalshi. Steps:
      1. ✅ keypair generated (`scripts/gen_polymarket_us_key.py`) — public key is at
         `secrets/polymarket_us_public_key.pem`.
      2. **You:** onboard at Polymarket US / email onboarding@qcex.com for API access,
         and **register that public key**.
      3. **You:** they return a **Client ID** (+ the env's **token URL** and
         **audience**). Put them in `.env` (`POLYMARKET_US_CLIENT_ID/TOKEN_URL/
         AUDIENCE`). Reads don't need KYC; trading later does.
      Then I can pull Polymarket US order books and MEASURE whether the Kalshi basis
      even exists on the legal venue (it may be much tighter — both are CFTC-regulated).
      Client is built + unit-tested; just needs your onboarding values.
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
