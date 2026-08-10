"""Dislocation analyzer detects an injected cross-venue lock and its persistence."""
from predarb.research.dislocation import analyze
from predarb.research.pairs import Pair
from predarb.research.mlb import team_of, two_teams


def _pair():
    return Pair(label="test", kalshi_ticker="K", poly_token="P", kind="total", polarity=1)


def test_no_dislocation_when_aligned():
    # both venues quote the same ~0.50 -> no positive lock after fees
    ticks = [
        {"ts": 1.0, "venue": "kalshi", "market_id": "K", "yes_bid": 0.49, "yes_ask": 0.51},
        {"ts": 1.1, "venue": "polymarket", "market_id": "P", "yes_bid": 0.49, "yes_ask": 0.51},
        {"ts": 2.0, "venue": "kalshi", "market_id": "K", "yes_bid": 0.49, "yes_ask": 0.51},
    ]
    st = analyze(ticks, _pair())
    assert st.n_both >= 1 and st.frac_dislocated == 0.0


def test_detects_lock_and_persistence():
    # kalshi YES ask 0.40, polymarket YES bid 0.55 -> buy kalshi/sell poly locks ~0.15
    ticks = [
        {"ts": 1.0, "venue": "kalshi", "market_id": "K", "yes_bid": 0.38, "yes_ask": 0.40},
        {"ts": 1.5, "venue": "polymarket", "market_id": "P", "yes_bid": 0.55, "yes_ask": 0.57},
        {"ts": 2.0, "venue": "kalshi", "market_id": "K", "yes_bid": 0.38, "yes_ask": 0.40},  # still open
        {"ts": 4.0, "venue": "polymarket", "market_id": "P", "yes_bid": 0.41, "yes_ask": 0.43},  # closes
    ]
    st = analyze(ticks, _pair())
    assert st.max_lock > 0.10
    assert st.n_episodes == 1
    assert st.max_episode_s >= 0.5   # persisted from t=1.5 to t=2.0+


def test_team_matching():
    assert team_of("Boston") == "BOS"
    assert team_of("Boston Red Sox") == "BOS"
    assert team_of("Chicago White Sox") == "CWS"
    assert two_teams("Baltimore Orioles vs. Minnesota Twins") == ("BAL", "MIN")
    assert two_teams("Boston vs Toronto Winner?") == ("BOS", "TOR")
