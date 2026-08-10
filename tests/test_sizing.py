"""Confidence-weighted sizing and its caps."""
from predarb.common.config import SafetyConfig, load_params
from predarb.common.types import Leg, Opportunity
from predarb.sizing.confidence import confidence, kelly_fraction, size_opportunity


def _opp(kind="dutch_book", edge=0.05, trust=1.0, matcher="curated", p_win=1.0, legs=None):
    legs = legs or [Leg("kalshi", "A", "yes", 0.40, 500), Leg("kalshi", "B", "no", 0.55, 500)]
    return Opportunity(group_key="g", kind=kind, legs=legs, edge=edge, consensus=0.5,
                       dispersion=0.1, p_win=p_win, trust=trust, matcher=matcher)


def test_kelly_fraction_basic():
    assert kelly_fraction(0.6, 0.5) > 0
    assert kelly_fraction(0.4, 0.5) == 0.0      # no edge -> no bet
    assert kelly_fraction(0.5, 0.0) == 0.0      # degenerate price


def test_dutch_book_confidence_is_high():
    assert confidence(_opp(kind="dutch_book"), load_params()) == 1.0


def test_cluster_matcher_dampens_confidence():
    params = load_params()
    base = confidence(_opp(kind="relative_value", edge=0.08, matcher="curated"), params)
    clustered = confidence(_opp(kind="relative_value", edge=0.08, matcher="cluster"), params)
    assert clustered < base


def test_size_respects_per_order_cap():
    s = SafetyConfig()
    s.max_contracts_per_order = 15
    s.max_notional_per_market_usd = 10_000
    s.max_notional_per_group_usd = 10_000
    s.bankroll_usd = 100_000
    qty = size_opportunity(_opp(), s, load_params())
    assert 0 < qty <= 15


def test_low_confidence_sizes_to_zero():
    params = load_params()
    params["confidence_floor"] = 0.99
    # a weak relative-value edge -> confidence below floor -> zero size
    qty = size_opportunity(_opp(kind="relative_value", edge=0.001, p_win=0.5), SafetyConfig(), params)
    assert qty == 0
