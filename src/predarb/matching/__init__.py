"""Matchers turn a flat list of markets into groups asserted to share an event."""
from __future__ import annotations

from .base import Matcher
from .cluster import ClusterMatcher
from .curated import CuratedMatcher
from .intraevent import IntraEventMatcher

ALL_MATCHERS: dict[str, type[Matcher]] = {
    "curated": CuratedMatcher,
    "intraevent": IntraEventMatcher,
    "cluster": ClusterMatcher,
}


def build_matcher(name: str, **kw) -> Matcher:
    if name not in ALL_MATCHERS:
        raise KeyError(f"unknown matcher {name!r}; have {list(ALL_MATCHERS)}")
    return ALL_MATCHERS[name](**kw)
