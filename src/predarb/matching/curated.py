"""Curated matcher — highest trust. Reads hand-written groups from config/groups.yaml.

Because a human asserts the equivalence, cross-member locks in these groups are
genuinely riskless. The only failure mode is a wrong grouping, so this file is the
one to audit most carefully.
"""
from __future__ import annotations

from pathlib import Path

from ..common.config import CONFIG_DIR
from ..common.logenv import get_logger
from ..common.types import GroupMember, MarketGroup, MarketRef

log = get_logger("matching.curated")

try:
    import yaml
except ImportError:
    yaml = None


class CuratedMatcher:
    name = "curated"

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else CONFIG_DIR / "groups.yaml"

    def build(self, refs: list[MarketRef]) -> list[MarketGroup]:
        if not yaml or not self.path.exists():
            log.warning("no curated groups file at %s", self.path)
            return []
        with open(self.path) as f:
            doc = yaml.safe_load(f) or {}
        groups = []
        for g in doc.get("groups", []):
            members = [
                GroupMember(
                    venue=m["venue"], market_id=str(m["market_id"]),
                    polarity=int(m.get("polarity", 1)),
                )
                for m in g.get("members", [])
            ]
            if len(members) < 2:
                continue
            groups.append(MarketGroup(
                key=g["key"], members=members,
                kind=g.get("kind", "equivalence"),
                trust=float(g.get("trust", 1.0)),
                matcher=self.name, note=g.get("note", ""),
            ))
        return groups
