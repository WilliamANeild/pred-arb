"""Sportsbook odds adapter (the-odds-api) — READ-ONLY consensus input.

US sportsbooks (DraftKings, FanDuel, Pinnacle, ...) expose lines but have no public
bet-placement API, so this venue is `fixed_odds` / not `executable`: its de-vigged
probabilities sharpen the group consensus, but the executor will never route an
order here (the quote carries no depth, and quote_only is True).

American odds -> implied prob, then two-way de-vig so the pair sums to 1.
"""
from __future__ import annotations

import time

import requests

from ..common.config import OddsConfig, odds as default_cfg
from ..common.logenv import get_logger
from ..common.types import Book, MarketRef, Snapshot
from .base import VenueAdapter

log = get_logger("venues.odds")

# A small default slate; override via list_markets(sports=[...]).
DEFAULT_SPORTS = ["basketball_nba", "americanfootball_nfl", "soccer_epl", "baseball_mlb"]


def american_to_prob(odds: float) -> float:
    """Implied win probability from American odds (still carries the vig)."""
    if odds >= 0:
        return 100.0 / (odds + 100.0)
    return -odds / (-odds + 100.0)


def devig_two_way(p_home_raw: float, p_away_raw: float) -> float:
    """Return the fair P(home) after removing the bookmaker's overround."""
    total = p_home_raw + p_away_raw
    return p_home_raw / total if total > 0 else p_home_raw


class OddsAdapter(VenueAdapter):
    name = "odds"
    env = "prod"
    market_type = "fixed_odds"
    executable = False

    def __init__(self, cfg: OddsConfig | None = None, session: requests.Session | None = None):
        self.cfg = cfg or default_cfg
        self.session = session or requests.Session()

    def list_markets(self, *, sports=None, limit=100, **_) -> list[MarketRef]:
        if not self.cfg.has_credentials():
            log.info("no ODDS_API_KEY set — odds adapter idle")
            return []
        out: list[MarketRef] = []
        for sport in (sports or DEFAULT_SPORTS):
            try:
                data = self.session.get(
                    f"{self.cfg.base_url}/sports/{sport}/odds",
                    params={"apiKey": self.cfg.api_key, "regions": self.cfg.regions,
                            "markets": "h2h", "oddsFormat": "american"},
                    timeout=20,
                ).json()
            except Exception as e:  # noqa: BLE001
                log.warning("odds fetch failed for %s: %s", sport, e)
                continue
            for ev in data if isinstance(data, list) else []:
                home = ev.get("home_team", "")
                away = ev.get("away_team", "")
                # market_id encodes the event + that YES == home team wins.
                out.append(MarketRef(
                    venue=self.name, market_id=f"{ev.get('id','')}::home",
                    title=f"{home} vs {away} (h2h)", event_id=ev.get("id", ""),
                    yes_meaning=f"{home} wins",
                ))
                if len(out) >= limit:
                    return out
        return out

    def get_snapshot(self, ref: MarketRef) -> Snapshot:
        """Consensus (median-book) de-vigged P(home). Quote-only: empty ladders so
        the signal layer treats it as an opinion, not a fillable market."""
        event_id = ref.event_id
        sport_probs: list[float] = []
        if self.cfg.has_credentials():
            for sport in DEFAULT_SPORTS:
                try:
                    data = self.session.get(
                        f"{self.cfg.base_url}/sports/{sport}/odds",
                        params={"apiKey": self.cfg.api_key, "regions": self.cfg.regions,
                                "markets": "h2h", "oddsFormat": "american", "eventIds": event_id},
                        timeout=20,
                    ).json()
                except Exception:  # noqa: BLE001
                    continue
                for ev in data if isinstance(data, list) else []:
                    if ev.get("id") != event_id:
                        continue
                    home = ev.get("home_team", "")
                    for bk in ev.get("bookmakers", []):
                        for mk in bk.get("markets", []):
                            outs = {o["name"]: o["price"] for o in mk.get("outcomes", [])}
                            names = list(outs)
                            if home in outs and len(names) == 2:
                                away = names[0] if names[1] == home else names[1]
                                sport_probs.append(devig_two_way(
                                    american_to_prob(outs[home]), american_to_prob(outs[away])))
        mid = sorted(sport_probs)[len(sport_probs) // 2] if sport_probs else None
        book = Book(yes_bid=mid, yes_ask=mid, yes_ask_levels=[], yes_bid_levels=[])
        return Snapshot(ref=ref, book=book, ts=time.time())
