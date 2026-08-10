"""The three matchers group markets as intended."""
from predarb.common.types import MarketRef
from predarb.matching.cluster import ClusterMatcher
from predarb.matching.curated import CuratedMatcher
from predarb.matching.intraevent import IntraEventMatcher


def test_intraevent_groups_shared_event():
    refs = [
        MarketRef("kalshi", "A", "cand A", "RACE1", ""),
        MarketRef("kalshi", "B", "cand B", "RACE1", ""),
        MarketRef("kalshi", "C", "cand C", "RACE2", ""),   # different event, alone
    ]
    groups = IntraEventMatcher().build(refs)
    assert len(groups) == 1
    g = groups[0]
    assert g.kind == "partition" and len(g.members) == 2 and g.trust == 1.0


def test_cluster_groups_similar_titles():
    refs = [
        MarketRef("kalshi", "A", "Will Bitcoin close above 100k in 2026", "e1"),
        MarketRef("polymarket", "B", "Bitcoin above 100k by end of 2026", "e2"),
        MarketRef("kalshi", "C", "Will it rain in Seattle tomorrow", "e3"),
    ]
    groups = ClusterMatcher(threshold=0.3).build(refs)
    # the two bitcoin markets cluster; the rain market stays out.
    assert any({m.market_id for m in g.members} == {"A", "B"} for g in groups)
    for g in groups:
        assert "C" not in {m.market_id for m in g.members}
        assert 0.0 < g.trust <= 1.0


def test_curated_loads_yaml(tmp_path):
    p = tmp_path / "groups.yaml"
    p.write_text(
        "groups:\n"
        "  - key: g1\n"
        "    kind: equivalence\n"
        "    trust: 1.0\n"
        "    members:\n"
        "      - {venue: kalshi, market_id: A, polarity: 1}\n"
        "      - {venue: polymarket, market_id: B, polarity: -1}\n"
    )
    groups = CuratedMatcher(path=p).build([])
    assert len(groups) == 1
    g = groups[0]
    assert g.key == "g1" and len(g.members) == 2
    assert g.members[1].polarity == -1
