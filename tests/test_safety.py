"""Real-money safety guards. These must never regress."""
from predarb.common.config import SafetyConfig
from predarb.common.types import Leg, Opportunity
from predarb.execute.safety import GateState, SafetyGate


def _opp(kind="dutch_book", legs=None, consensus=0.5, edge=0.05, trust=1.0, matcher="curated"):
    legs = legs or [Leg("kalshi", "M1", "yes", 0.40, 20), Leg("kalshi", "M2", "no", 0.55, 20)]
    return Opportunity(group_key="g", kind=kind, legs=legs, edge=edge,
                       consensus=consensus, dispersion=0.1, trust=trust, matcher=matcher)


def _gate(**overrides):
    s = SafetyConfig()
    for k, v in overrides.items():
        setattr(s, k, v)
    return SafetyGate(s, GateState())


def test_live_requires_all_gates():
    s = SafetyConfig(); s.allow_live_trading = True
    assert s.live_allowed("prod", True) is True
    assert s.live_allowed("demo", True) is False      # not prod
    assert s.live_allowed("prod", False) is False     # no run flag
    s.kill_switch = True
    assert s.live_allowed("prod", True) is False       # kill switch


def test_live_riskless_only_blocks_relval():
    g = _gate(allow_live_trading=True, live_riskless_only=True)
    opp = _opp(kind="relative_value")
    assert g.live_guard(opp, "prod", True) is not None      # relval blocked
    assert g.live_guard(_opp(kind="dutch_book"), "prod", True) is None


def test_live_blocks_thin_edge():
    g = _gate(allow_live_trading=True, min_edge_live=0.07)
    assert g.live_guard(_opp(edge=0.04), "prod", True) is not None


def test_cluster_trust_floor():
    g = _gate(allow_live_trading=True, live_riskless_only=False, cluster_trust_floor=0.80)
    assert g.live_guard(_opp(matcher="cluster", trust=0.6), "prod", True) is not None
    assert g.live_guard(_opp(matcher="cluster", trust=0.9), "prod", True) is None


def test_consensus_band_blocks_tails():
    g = _gate()
    assert g.check(_opp(consensus=0.05), 5) is not None     # longshot tail
    assert g.check(_opp(consensus=0.50), 5) is None


def test_per_order_cap():
    g = _gate(max_contracts_per_order=20)
    assert g.check(_opp(), 30) is not None
    assert g.check(_opp(), 10) is None


def test_max_price_guard():
    g = _gate(max_price_cents=97)
    assert g.check(_opp(legs=[Leg("kalshi", "M", "yes", 0.98, 20)]), 5) is not None


def test_total_notional_cap():
    g = _gate(max_total_notional_usd=100.0, max_notional_per_market_usd=1000.0,
              max_notional_per_group_usd=1000.0)
    g.state.total_notional = 95.0
    assert g.check(_opp(legs=[Leg("kalshi", "M", "yes", 0.50, 20)]), 20) is not None


def test_daily_loss_limit_halts():
    g = _gate(daily_loss_limit_usd=50.0)
    g.state.realized_loss = 51.0
    assert g.check(_opp(), 5) is not None


def test_kill_switch_blocks(tmp_path):
    import predarb.common.config as cfg
    orig = cfg.DATA_DIR
    cfg.DATA_DIR = tmp_path
    try:
        g = _gate()
        assert g.check(_opp(), 5) is None
        g.safety.kill_switch = True
        assert g.check(_opp(), 5) is not None
    finally:
        cfg.DATA_DIR = orig


def test_consecutive_error_breaker_engages_kill(tmp_path):
    import predarb.common.config as cfg
    orig = cfg.DATA_DIR
    cfg.DATA_DIR = tmp_path
    try:
        g = _gate(max_consecutive_errors=2)
        g.note_error()
        assert not g.safety.kill_engaged()
        g.note_error()
        assert g.safety.kill_engaged()      # kill file written on 2nd error
    finally:
        cfg.DATA_DIR = orig


def test_stale_feed_blocks():
    g = _gate(feed_staleness_seconds=60)
    assert g.check(_opp(), 5, snap_ts=0.0, now=1000.0) is not None
    assert g.check(_opp(), 5, snap_ts=990.0, now=1000.0) is None


def test_defaults_are_paper_only():
    s = SafetyConfig()
    assert s.allow_live_trading is False
    assert s.live_riskless_only is True
