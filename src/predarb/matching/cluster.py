"""Cluster matcher — lowest trust. Groups markets across events by title similarity.

This is the risky one: a false match becomes hidden basis risk, so groups here get
a `trust` equal to their similarity score, which downstream sizing uses to shrink
(or, for real money, forbid) positions. Pure-stdlib token-Jaccard clustering — no
heavy NLP dependency for the POC; upgrade to embeddings later.
"""
from __future__ import annotations

import re

from ..common.types import GroupMember, MarketGroup, MarketRef

_STOP = {
    "the", "a", "an", "will", "be", "to", "of", "in", "on", "at", "for", "and",
    "or", "is", "are", "by", "this", "that", "than", "before", "after", "market",
    "yes", "no", "does", "do", "did", "with", "as", "it",
}


def _tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w for w in words if w not in _STOP and len(w) > 1}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / len(a | b)


class ClusterMatcher:
    name = "cluster"

    def __init__(self, threshold: float = 0.5, min_members: int = 2):
        self.threshold = threshold
        self.min_members = min_members

    def build(self, refs: list[MarketRef]) -> list[MarketGroup]:
        toks = [(_tokens(r.title or r.yes_meaning), r) for r in refs]
        toks = [(t, r) for t, r in toks if t]
        n = len(toks)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        # Union markets whose titles are similar enough. Track the min pairwise
        # similarity within each merge as the group's trust (conservative).
        sims: dict[tuple[int, int], float] = {}
        for i in range(n):
            for j in range(i + 1, n):
                s = _jaccard(toks[i][0], toks[j][0])
                if s >= self.threshold:
                    sims[(i, j)] = s
                    parent[find(i)] = find(j)

        clusters: dict[int, list[int]] = {}
        for i in range(n):
            clusters.setdefault(find(i), []).append(i)

        groups = []
        for root, idxs in clusters.items():
            if len(idxs) < self.min_members:
                continue
            # trust = mean similarity among matched pairs inside this cluster
            pair_scores = [sims[(a, b)] for a in idxs for b in idxs
                           if a < b and (a, b) in sims]
            trust = sum(pair_scores) / len(pair_scores) if pair_scores else self.threshold
            members = [GroupMember(venue=toks[i][1].venue, market_id=toks[i][1].market_id, polarity=1)
                       for i in idxs]
            titles = "; ".join(toks[i][1].title for i in idxs)[:120]
            groups.append(MarketGroup(
                key=f"cluster:{root}", members=members, kind="equivalence",
                trust=round(trust, 3), matcher=self.name, note=titles,
            ))
        return groups
