"""Intra-event matcher — groups the mutually-exclusive outcomes of one event.

Structural and near-riskless: markets sharing an `event_id` (e.g. every candidate
in one race, every bucket of one number line) form a partition whose YES
probabilities should sum to ~1. This is the author's hypothesized best matcher.
"""
from __future__ import annotations

from collections import defaultdict

from ..common.types import GroupMember, MarketGroup, MarketRef


class IntraEventMatcher:
    name = "intraevent"

    def __init__(self, min_members: int = 2):
        self.min_members = min_members

    def build(self, refs: list[MarketRef]) -> list[MarketGroup]:
        by_event: dict[str, list[MarketRef]] = defaultdict(list)
        for r in refs:
            if r.event_id:
                by_event[f"{r.venue}:{r.event_id}"].append(r)

        groups = []
        for event_key, members in by_event.items():
            if len(members) < self.min_members:
                continue
            gm = [GroupMember(venue=m.venue, market_id=m.market_id, polarity=1) for m in members]
            groups.append(MarketGroup(
                key=f"intraevent:{event_key}", members=gm,
                kind="partition", trust=1.0, matcher=self.name,
                note=f"{len(gm)} mutually-exclusive outcomes",
            ))
        return groups
