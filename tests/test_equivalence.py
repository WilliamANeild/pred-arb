"""The structured equivalence guard must reject the real false-match cases we saw
live, and accept genuinely-identical contracts."""
from predarb.signal.equivalence import extract, is_equivalent


def test_rejects_different_line():
    ok, reason = is_equivalent(
        "Milwaukee vs San Diego first 5 innings runs? Over 6.5",
        "Milwaukee Brewers vs. San Diego Padres: O/U 7.5")
    assert not ok and "threshold" in reason


def test_rejects_inverted_polarity():
    ok, reason = is_equivalent(
        "Bitcoin price on Aug 10, 2026? $62,000 or above",
        "Will Bitcoin dip to $62,000 August 10-16?")
    assert not ok and "direction" in reason


def test_rejects_date_shift():
    ok, reason = is_equivalent(
        "Bitcoin price on Aug 10, 2026? $62,000 or above",
        "Will the price of Bitcoin be above $62,000 on August 12?")
    assert not ok and "date" in reason


def test_accepts_true_match():
    ok, reason = is_equivalent(
        "Bitcoin above $62,000 on August 12",
        "Will the price of Bitcoin be above $62,000 on August 12?")
    assert ok


def test_rejects_game_vs_season():
    # same player + "home runs", but one is a single game, the other the season lead
    ok, _ = is_equivalent(
        "Yordan Alvarez: 2+ home runs?",
        "Will Yordan Alvarez hit the most home runs during the 2026 MLB season?")
    assert not ok   # "2" vs no matching season number -> threshold mismatch


def test_extract_basics():
    f = extract("Bitcoin above $100,000 on Dec 31")
    assert 100000.0 in f.numbers and f.direction == "up" and f.date == (12, 31)
