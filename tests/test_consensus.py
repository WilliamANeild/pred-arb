"""Consensus math, entry-price mapping, and lock/relval detection."""
from predarb.common.config import SafetyConfig, load_params
from predarb.common.types import Book, GroupMember, MarketGroup, MarketRef, Snapshot
from predarb.signal.consensus import compute_consensus, entry_price, member_event_prob
from predarb.signal.profiles import RelativeValueProfile, RisklessOnly


def _snap(venue, mid, spread=0.02, depth=100, settle=None):
    ref = MarketRef(venue, "X", "t", "e", "Yes")
    ask, bid = mid + spread / 2, mid - spread / 2
    book = Book(yes_bid=bid, yes_ask=ask,
                yes_ask_levels=[(ask, depth)], yes_bid_levels=[(bid, depth)])
    return Snapshot(ref, book, ts=1_700_000_000, settle=settle)


def test_polarity_inversion():
    b = _snap("kalshi", 0.30).book
    assert abs(member_event_prob(GroupMember("kalshi", "X", 1), b) - 0.30) < 1e-9
    assert abs(member_event_prob(GroupMember("kalshi", "X", -1), b) - 0.70) < 1e-9


def test_entry_price_event_sides():
    b = _snap("kalshi", 0.40, spread=0.04).book  # ask 0.42 bid 0.38
    side, price, qty = entry_price(GroupMember("kalshi", "X", 1), b, "event_yes")
    assert side == "yes" and abs(price - 0.42) < 1e-9
    side, price, qty = entry_price(GroupMember("kalshi", "X", 1), b, "event_no")
    assert side == "no" and abs(price - (1 - 0.38)) < 1e-9   # no-ask = 1 - yes_bid


def _group(members, kind="equivalence"):
    return MarketGroup(key="g", members=members, kind=kind, trust=1.0, matcher="curated")


def test_pair_lock_detected_when_crossed():
    # A cheap (mid 0.30), B rich (mid 0.70): buy E-yes on A (ask .31) + E-no on B
    # (no-ask = 1-0.69 = .31) -> cost ~.62 < 1 -> lock.
    snaps = {"kalshi:A": _snap("kalshi", 0.30), "kalshi:B": _snap("kalshi", 0.70)}
    snaps["kalshi:A"].ref = MarketRef("kalshi", "A")
    snaps["kalshi:B"].ref = MarketRef("kalshi", "B")
    grp = _group([GroupMember("kalshi", "A", 1), GroupMember("kalshi", "B", 1)])
    params = load_params()
    opps = RisklessOnly().evaluate(grp, snaps, params, SafetyConfig())
    assert any(o.kind == "dutch_book" and o.edge > 0 for o in opps)


def test_partition_underround_lock():
    # three outcomes priced to sum < 1 -> buy all -> lock.
    snaps = {}
    for name, mid in [("A", 0.30), ("B", 0.30), ("C", 0.30)]:
        s = _snap("kalshi", mid); s.ref = MarketRef("kalshi", name, "t", "evt", "Yes")
        snaps[f"kalshi:{name}"] = s
    grp = _group([GroupMember("kalshi", "A", 1), GroupMember("kalshi", "B", 1),
                  GroupMember("kalshi", "C", 1)], kind="partition")
    opps = RisklessOnly().evaluate(grp, snaps, load_params(), SafetyConfig())
    assert opps and opps[0].edge > 0
    assert len(opps[0].legs) == 3


def test_relative_value_on_outlier():
    # consensus ~0.55; one member at 0.40 is the underpriced outlier -> buy E-yes.
    snaps = {}
    for name, mid in [("A", 0.56), ("B", 0.55), ("C", 0.40)]:
        s = _snap("kalshi", mid, spread=0.02, depth=200)
        s.ref = MarketRef("kalshi", name, "t", f"e{name}", "Yes")
        snaps[f"kalshi:{name}"] = s
    grp = _group([GroupMember("kalshi", "A", 1), GroupMember("kalshi", "B", 1),
                  GroupMember("kalshi", "C", 1)])
    params = load_params()
    opps = RelativeValueProfile().evaluate(grp, snaps, params, SafetyConfig())
    assert opps and opps[0].kind == "relative_value"
    assert opps[0].legs[0].market_id == "C"


def test_no_consensus_below_two_members():
    grp = _group([GroupMember("kalshi", "A", 1)])
    assert compute_consensus(grp, {"kalshi:A": _snap("kalshi", 0.5)}, load_params()) is None
