"""Sportsbook odds: American->prob, de-vig, and the quote-only capability."""
from predarb.venues.odds import OddsAdapter, american_to_prob, devig_two_way


def test_american_to_prob():
    assert abs(american_to_prob(+100) - 0.5) < 1e-9
    assert abs(american_to_prob(-200) - (200 / 300)) < 1e-9
    assert abs(american_to_prob(+150) - (100 / 250)) < 1e-9


def test_devig_sums_to_one():
    ph = american_to_prob(-150)   # favorite, raw > 0.5
    pa = american_to_prob(+130)
    fair_home = devig_two_way(ph, pa)
    fair_away = devig_two_way(pa, ph)
    assert abs((fair_home + fair_away) - 1.0) < 1e-9
    assert fair_home > 0.5        # favorite stays the favorite after de-vig


def test_odds_venue_is_quote_only():
    a = OddsAdapter()
    assert a.market_type == "fixed_odds"
    assert a.executable is False
    assert a.quote_only is True
    assert a.supports_trading() is False


def test_no_key_lists_nothing():
    from predarb.common.config import OddsConfig
    a = OddsAdapter(OddsConfig(enabled=True, api_key=""))
    assert a.list_markets() == []
