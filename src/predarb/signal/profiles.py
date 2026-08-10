"""Risk profiles: turn a group's consensus into concrete opportunities.

Three profiles, each backtested against the others by the grid:
  - riskless_only  : dutch-book locks only (guaranteed profit if grouping is right)
  - relative_value : convergence trades only (basis risk; gated + capped)
  - both           : locks preferred; convergence added for groups with no lock
"""
from __future__ import annotations

from itertools import combinations

from ..common.config import SafetyConfig
from ..common.types import Leg, MarketGroup, Opportunity, Snapshot
from .consensus import ConsensusResult, compute_consensus, entry_price
from .fees import fee_per_contract


def _in_band(consensus: float, params: dict) -> bool:
    return params["min_consensus"] <= consensus <= params["max_consensus"]


def _leg(member, venue_side, price, qty) -> Leg:
    return Leg(venue=member.venue, market_id=member.market_id,
               side=venue_side, price=price, qty=int(qty))


def find_locks(group: MarketGroup, cons: ConsensusResult, snaps: dict[str, Snapshot],
               params: dict) -> list[Opportunity]:
    """Riskless dutch-book locks: pair locks (equivalence) or under-round (partition)."""
    out: list[Opportunity] = []
    min_edge = params["riskless_min_edge"]

    if group.kind == "partition":
        # Buy every outcome's YES; exactly one settles $1. Lock if Σask + fees < 1.
        legs, total_cost, min_qty = [], 0.0, None
        ok = True
        for v in cons.views:
            e = entry_price(v.member, v.snap.book, "event_yes")
            if e is None:
                ok = False
                break
            side, price, qty = e
            fee = fee_per_contract(v.member.venue, price, params)
            total_cost += price + fee
            min_qty = qty if min_qty is None else min(min_qty, qty)
            legs.append(_leg(v.member, side, price, qty))
        if ok and min_qty and min_qty > 0:
            edge = 1.0 - total_cost
            if edge >= min_edge:
                for lg in legs:
                    lg.qty = int(min_qty)
                out.append(Opportunity(
                    group_key=group.key, kind="dutch_book", legs=legs, edge=edge,
                    consensus=cons.consensus, dispersion=cons.dispersion,
                    trust=group.trust, matcher=group.matcher,
                    note=f"partition under-round: Σask={total_cost:.3f}",
                ))
        return out

    # equivalence: scan member pairs for buy-E-yes(A) + buy-E-no(B) < 1
    for a, b in combinations(cons.views, 2):
        for ya, nb in ((a, b), (b, a)):
            ea = entry_price(ya.member, ya.snap.book, "event_yes")
            eb = entry_price(nb.member, nb.snap.book, "event_no")
            if ea is None or eb is None:
                continue
            (sa, pa, qa), (sb, pb, qb) = ea, eb
            fee = (fee_per_contract(ya.member.venue, pa, params)
                   + fee_per_contract(nb.member.venue, pb, params))
            edge = 1.0 - (pa + pb + fee)
            qty = min(qa, qb)
            if edge >= min_edge and qty > 0:
                out.append(Opportunity(
                    group_key=group.key, kind="dutch_book",
                    legs=[_leg(ya.member, sa, pa, qty), _leg(nb.member, sb, pb, qty)],
                    edge=edge, consensus=cons.consensus, dispersion=cons.dispersion,
                    trust=group.trust, matcher=group.matcher,
                    note=f"pair lock {ya.member.key} Eyes@{pa:.3f} + {nb.member.key} Eno@{pb:.3f}",
                ))
    return out


def find_relval(group: MarketGroup, cons: ConsensusResult, params: dict) -> list[Opportunity]:
    """Relative-value convergence trade on the group's largest-deviation member."""
    if cons.dispersion < params["dispersion_min"]:
        return []
    v = cons.outlier
    if v is None or abs(v.deviation) < params["deviation_threshold"]:
        return []

    # deviation < 0 -> member under-prices E-yes -> buy E-yes; else buy E-no.
    want = "event_yes" if v.deviation < 0 else "event_no"
    e = entry_price(v.member, v.snap.book, want)
    if e is None:
        return []
    side, price, qty = e
    if qty <= 0:
        return []
    target = cons.consensus if want == "event_yes" else (1.0 - cons.consensus)
    fee = fee_per_contract(v.member.venue, price, params)
    edge = target - price - fee
    if edge < params["relval_min_edge"]:
        return []
    return [Opportunity(
        group_key=group.key, kind="relative_value",
        legs=[_leg(v.member, side, price, qty)],
        edge=edge, consensus=cons.consensus, dispersion=cons.dispersion,
        p_win=target, trust=group.trust, matcher=group.matcher,
        note=f"outlier {v.member.key} dev={v.deviation:+.3f} buy {want}@{price:.3f}->{target:.3f}",
    )]


class RiskProfile:
    name = "base"

    def evaluate(self, group: MarketGroup, snaps: dict[str, Snapshot], params: dict,
                 safety: SafetyConfig) -> list[Opportunity]:
        cons = compute_consensus(group, snaps, params)
        if cons is None or not _in_band(cons.consensus, params):
            return []
        return self._emit(group, cons, snaps, params)

    def _emit(self, group, cons, snaps, params):  # pragma: no cover - overridden
        raise NotImplementedError


class RisklessOnly(RiskProfile):
    name = "riskless_only"

    def _emit(self, group, cons, snaps, params):
        return find_locks(group, cons, snaps, params)


class RelativeValueProfile(RiskProfile):
    name = "relative_value"

    def _emit(self, group, cons, snaps, params):
        return find_relval(group, cons, params)


class BothProfile(RiskProfile):
    name = "both"

    def _emit(self, group, cons, snaps, params):
        locks = find_locks(group, cons, snaps, params)
        if locks:
            return locks   # prefer the guaranteed profit; skip basis-risk trade
        return find_relval(group, cons, params)


ALL_PROFILES: dict[str, type[RiskProfile]] = {
    "riskless_only": RisklessOnly,
    "relative_value": RelativeValueProfile,
    "both": BothProfile,
}


def build_profile(name: str) -> RiskProfile:
    if name not in ALL_PROFILES:
        raise KeyError(f"unknown profile {name!r}; have {list(ALL_PROFILES)}")
    return ALL_PROFILES[name]()
