"""Consensus engine: normalize a group's members to a common event probability,
measure dispersion/deviation, and expose tradeable entry prices.

Everything is expressed in terms of the group's binary event E. Each member has a
polarity: +1 means member-YES == E-yes; -1 means member-YES == E-no.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..common.types import Book, GroupMember, MarketGroup, Snapshot


@dataclass
class MemberView:
    member: GroupMember
    snap: Snapshot
    p_event: float          # implied P(E=yes) from this member's mid
    deviation: float = 0.0  # p_event - consensus
    weight: float = 1.0


@dataclass
class ConsensusResult:
    group_key: str
    consensus: float               # p*(E=yes)
    dispersion: float              # max p_event - min p_event
    views: list[MemberView]

    @property
    def outlier(self) -> Optional[MemberView]:
        """Member furthest from consensus (largest |deviation|)."""
        return max(self.views, key=lambda v: abs(v.deviation), default=None)


def member_event_prob(member: GroupMember, book: Book) -> Optional[float]:
    mid = book.mid
    if mid is None:
        return None
    return mid if member.polarity == 1 else 1.0 - mid


def entry_price(member: GroupMember, book: Book, want: str) -> Optional[tuple[str, float, int]]:
    """How to BUY the E-side `want` ("event_yes"|"event_no") through this member.

    Returns (venue_side, price_prob, qty_available) or None if that side isn't
    quoted. venue_side is what we actually submit to the venue ("yes"/"no").
    """
    # Buying E-yes: if polarity +1 buy member-YES (at yes_ask); if -1 buy member-NO.
    # Buying E-no is the mirror.
    buy_member_yes = (want == "event_yes") == (member.polarity == 1)
    if buy_member_yes:
        if book.yes_ask is None:
            return None
        return ("yes", book.yes_ask, book.yes_ask_qty)
    else:
        no_ask = book.no_ask
        if no_ask is None:
            return None
        levels = book.no_ask_levels()
        qty = levels[0][1] if levels else 0
        return ("no", no_ask, qty)


def compute_consensus(group: MarketGroup, snaps: dict[str, Snapshot],
                      params: dict) -> Optional[ConsensusResult]:
    """Build consensus for a group given a {market_key: Snapshot} map. Returns None
    if fewer than two members have a usable mid."""
    views: list[MemberView] = []
    for m in group.members:
        snap = snaps.get(m.key)
        if snap is None:
            continue
        p = member_event_prob(m, snap.book)
        if p is None:
            continue
        views.append(MemberView(member=m, snap=snap, p_event=p))

    if len(views) < 2:
        return None

    if params.get("weight_by_liquidity", True):
        for v in views:
            depth = v.snap.book.yes_ask_qty + v.snap.book.yes_bid_qty
            v.weight = float(max(depth, 1))
    total_w = sum(v.weight for v in views) or 1.0
    consensus = sum(v.p_event * v.weight for v in views) / total_w

    ps = [v.p_event for v in views]
    dispersion = max(ps) - min(ps)
    for v in views:
        v.deviation = v.p_event - consensus

    return ConsensusResult(group_key=group.key, consensus=consensus,
                           dispersion=dispersion, views=views)
