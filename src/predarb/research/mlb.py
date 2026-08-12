"""MLB cross-venue pair discovery.

Matches identical MLB game markets across Kalshi and Polymarket:
  * moneyline — Kalshi KXMLBGAME "A vs B Winner?" (one market per team, YES=team
    wins) <-> Polymarket "City Team vs. City Team" (outcome token per team).
  * total    — Kalshi KXMLBTOTAL "A vs B Total Runs? Over X" <-> Polymarket
    "... O/U X" (outcomes Over/Under).

Teams are matched by token overlap against a team dictionary (Kalshi uses cities,
Polymarket uses "City Nickname"), so "Boston" <-> "Boston Red Sox" and
"Chicago WS" <-> "Chicago White Sox" both resolve. Anchored on Kalshi KXMLB tickers,
so a match is unambiguously an MLB game.
"""
from __future__ import annotations

import json
import re

import requests

from ..common.logenv import get_logger
from ..venues.kalshi_client import KalshiClient
from .pairs import Pair

log = get_logger("research.mlb")

# code -> identifying tokens (city + nickname). Nicknames disambiguate shared cities.
MLB_TEAMS = {
    "BAL": {"baltimore", "orioles"}, "BOS": {"boston", "red", "sox"},
    "NYY": {"yankees"}, "TB": {"tampa", "bay", "rays"}, "TOR": {"toronto", "blue", "jays"},
    "CWS": {"white", "sox", "ws"}, "CLE": {"cleveland", "guardians"},
    "DET": {"detroit", "tigers"}, "KC": {"kansas", "city", "royals"},
    "MIN": {"minnesota", "twins"}, "HOU": {"houston", "astros"},
    "LAA": {"angels"}, "OAK": {"oakland", "athletics"},
    "SEA": {"seattle", "mariners"}, "TEX": {"texas", "rangers"},
    "ATL": {"atlanta", "braves"}, "MIA": {"miami", "marlins"},
    "NYM": {"mets"}, "PHI": {"philadelphia", "phillies"},
    "WSH": {"washington", "nationals"}, "CHC": {"cubs"},
    "CIN": {"cincinnati", "reds"}, "MIL": {"milwaukee", "brewers"},
    "PIT": {"pittsburgh", "pirates"}, "STL": {"louis", "cardinals"},
    "ARI": {"arizona", "diamondbacks"}, "COL": {"colorado", "rockies"},
    "LAD": {"dodgers"}, "SD": {"san", "diego", "padres"}, "SF": {"francisco", "giants"},
}


def _toks(s):
    return {w for w in re.findall(r"[a-z]+", (s or "").lower())}


def team_of(fragment: str) -> str | None:
    t = _toks(fragment)
    best, score = None, 0
    for code, keys in MLB_TEAMS.items():
        o = len(t & keys)
        if o > score:
            best, score = code, o
    return best if score > 0 else None


def two_teams(title: str) -> tuple[str | None, str | None]:
    parts = re.split(r"\s+vs\.?\s+", title, maxsplit=1, flags=re.I)
    if len(parts) != 2:
        return (None, None)
    return (team_of(parts[0]), team_of(parts[1]))


def _line(s: str) -> float | None:
    m = re.search(r"(\d+\.5)\b", s)
    return float(m.group(1)) if m else None


_MON = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def kalshi_game_date(ticker: str) -> tuple[int, int] | None:
    """(month, day) from a Kalshi MLB ticker code like '26AUG131507'."""
    m = re.search(r"-\d{2}([A-Z]{3})(\d{2})\d{4}", ticker)
    if not m or m.group(1) not in _MON:
        return None
    return (_MON[m.group(1)], int(m.group(2)))


def poly_game_date(game_start: str) -> tuple[int, int] | None:
    """(month, day) from Polymarket gameStartTime like '2026-08-10 23:07:00+00'."""
    m = re.search(r"\d{4}-(\d{2})-(\d{2})", game_start or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def _fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _liquid(bid, ask) -> bool:
    """Genuine two-sided book. Off-main-line Kalshi totals are one-sided/degenerate
    (0/0, 0.02/0.98) and manufacture fake locks — exclude them at discovery time."""
    if bid is None or ask is None:
        return False
    return 0.03 <= bid < ask <= 0.97 and (ask - bid) <= 0.12


KALSHI_MLB_SERIES = ("KXMLBGAME", "KXMLBTOTAL")


def _pull_kalshi_mlb():
    """Query each MLB series directly — reliably surfaces TODAY's games, unlike
    paging the 10k-market generic feed."""
    c = KalshiClient()
    out = []
    for series in KALSHI_MLB_SERIES:
        cur, pg = None, 0
        while pg < 10:
            p = {"series_ticker": series, "status": "open", "limit": 200}
            if cur:
                p["cursor"] = cur
            r = c._request("GET", "/markets", params=p)
            for m in r.get("markets", []):
                if " vs" in m.get("title", "").lower():
                    out.append(m)
            cur = r.get("cursor")
            pg += 1
            if not cur:
                break
    return out


def _pull_poly_mlb():
    out, off = [], 0
    for _ in range(6):
        r = requests.get("https://gamma-api.polymarket.com/markets",
                         params={"limit": 500, "offset": off, "active": "true", "closed": "false",
                                 "order": "volume24hr", "ascending": "false"}, timeout=25).json()
        rows = r if isinstance(r, list) else r.get("data", [])
        if not rows:
            break
        for m in rows:
            q = m.get("question", "")
            a, b = two_teams(q)
            if a and b:                       # both sides resolve to MLB teams
                ids = m.get("clobTokenIds")
                if isinstance(ids, str):
                    try:
                        ids = json.loads(ids)
                    except json.JSONDecodeError:
                        ids = []
                out.append({"q": q, "teams": frozenset((a, b)), "outcomes": m.get("outcomes"),
                            "ids": ids, "line": _line(q), "bid": _fnum(m.get("bestBid")),
                            "ask": _fnum(m.get("bestAsk")),
                            "date": poly_game_date(m.get("gameStartTime", ""))})
        off += 500
    return out


def _poly_outcome_teams(p):
    outs = p["outcomes"]
    if isinstance(outs, str):
        try:
            outs = json.loads(outs)
        except json.JSONDecodeError:
            outs = []
    return [team_of(o) for o in (outs or [])]


def discover_mlb_pairs() -> list[Pair]:
    kal = _pull_kalshi_mlb()
    poly = _pull_poly_mlb()
    log.info("kalshi MLB markets=%d, polymarket MLB markets=%d", len(kal), len(poly))
    pairs: list[Pair] = []

    for m in kal:
        tk = m.get("ticker", "")
        title = m.get("title", "")
        a, b = two_teams(title)
        if not (a and b):
            continue
        kdate = kalshi_game_date(tk)
        if kdate is None:
            continue
        # only trade Kalshi markets that are actually two-sided liquid right now.
        if not _liquid(_fnum(m.get("yes_bid_dollars")), _fnum(m.get("yes_ask_dollars"))):
            continue
        game = frozenset((a, b))
        # SAME teams AND SAME game date — a 3-days-apart "match" is a different game.
        pm = [p for p in poly if p["teams"] == game and p["date"] == kdate
              and _liquid(p["bid"], p["ask"])]
        if not pm:
            continue
        datelbl = f"{kdate[0]:02d}/{kdate[1]:02d}"

        if tk.startswith("KXMLBGAME"):
            yes_team = team_of(m.get("yes_sub_title", ""))
            if not yes_team:
                continue
            # find a polymarket moneyline (2 team outcomes, no line) for this game
            for p in pm:
                if p["line"] is not None or not p["ids"] or len(p["ids"]) < 2:
                    continue
                ot = _poly_outcome_teams(p)
                if yes_team in ot:
                    tok = p["ids"][ot.index(yes_team)]
                    pairs.append(Pair(label=f"MLB ML {a}v{b} {datelbl} YES={yes_team}",
                                      kalshi_ticker=tk, poly_token=str(tok),
                                      kind="moneyline", polarity=1))
                    break

        elif tk.startswith("KXMLBTOTAL"):
            # Kalshi puts the line in the sub-title ("Over 8.5 runs scored").
            line = _line(m.get("yes_sub_title", "")) or _line(title)
            if line is None:
                continue
            for p in pm:
                if p["line"] is None or p["line"] != line or not p["ids"]:
                    continue
                ot = [str(o).lower() for o in (json.loads(p["outcomes"]) if isinstance(p["outcomes"], str) else p["outcomes"] or [])]
                over_idx = ot.index("over") if "over" in ot else 0
                pairs.append(Pair(label=f"MLB TOT {a}v{b} {datelbl} Over {line}",
                                  kalshi_ticker=tk, poly_token=str(p["ids"][over_idx]),
                                  kind="total", line=line, polarity=1))
                break
    return pairs
