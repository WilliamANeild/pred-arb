"""Ladder-monotonicity lock math, threshold parsing, and game-freshness filter."""
import time

from predarb.research.ladders import (_is_fresh, _threshold, game_epoch,
                                       ladder_lock_edge)


def test_normal_ordering_is_no_lock():
    # Over 6.5 asks 0.40, Over 7.5 bids 0.30 (correctly lower) -> no lock
    assert ladder_lock_edge(ask_lo=0.40, bid_hi=0.30) < 0


def test_inversion_is_a_lock():
    # higher threshold bid 0.55 exceeds lower threshold ask 0.40 -> inversion lock
    assert ladder_lock_edge(ask_lo=0.40, bid_hi=0.55) > 0


def test_threshold_parsing():
    assert _threshold("KX-...-3", "Charles McAdoo: 3+") == 3.0
    assert _threshold("KX-...-9", "Over 8.5 runs scored") == 8.5
    assert _threshold("KXMLBHIT-...-2", "") == 2.0   # falls back to ticker suffix


def test_game_epoch_and_freshness():
    tk = "KXMLBTOTAL-26AUG101907BOSTOR-8"
    ge = game_epoch(tk)
    assert ge is not None
    # fresh relative to its own game time; stale two weeks later
    assert _is_fresh(tk, ge + 3600, hours_back=6, days_fwd=3) is True
    assert _is_fresh(tk, ge + 14 * 86400, hours_back=6, days_fwd=3) is False
