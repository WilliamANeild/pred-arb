"""Fill simulation and fees."""
from predarb.backtest.fills import simulate_fill, walk_book
from predarb.signal.fees import kalshi_fee_usd


def test_walk_book_haircut_and_vwap():
    levels = [(0.40, 100), (0.41, 100)]
    filled, vwap = walk_book(levels, want=100, haircut=0.5)  # only 50/level available
    assert filled == 100
    assert abs(vwap - (50 * 0.40 + 50 * 0.41) / 100) < 1e-9


def test_partial_fill_when_book_thin():
    fill = simulate_fill([(0.40, 20)], want=100, haircut=0.5)  # only 10 available
    assert fill.filled == 10 and fill.filled < 100


def test_empty_book_no_fill():
    assert simulate_fill([], want=10).filled == 0


def test_kalshi_fee_positive_and_zero_at_edges():
    assert kalshi_fee_usd(0.50, 100) > 0
    assert kalshi_fee_usd(1.0, 100) == 0.0   # p*(1-p)=0 at the boundary


def test_polymarket_has_no_fee():
    fill = simulate_fill([(0.50, 1000)], want=100, venue="polymarket")
    assert fill.fee_usd == 0.0
