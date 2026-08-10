"""Synthetic market generator — lets the whole pipeline (matchers, signal, sizing,
harness, grid) run end-to-end with NO network and NO keys, and gives the tests a
deterministic fixture. Two structures are produced so every matcher has something
to find:

  * equivalence duplicates  — the same event quoted on two venues with the SAME
    title but different event ids (found by `cluster` and by `curated`); early
    frames are deliberately crossed so a riskless pair-lock exists, then converge.
  * partition events         — K mutually-exclusive outcomes sharing one event id
    (found by `intraevent`), priced under-round early so an under-round lock exists.

`settle` is stamped onto the final frame so relative-value PnL can resolve.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from ..common.types import Book, GroupMember, MarketGroup, MarketRef, Snapshot
from ..recorder.store import Frame

BASE_TS = 1_700_000_000


def _clamp(x: float, lo=0.02, hi=0.98) -> float:
    return max(lo, min(hi, x))


def _book(mid: float, spread: float, depth: int, levels: int = 3) -> Book:
    ask = _clamp(mid + spread / 2)
    bid = _clamp(mid - spread / 2)
    ask_levels = [(_clamp(ask + 0.01 * k), depth) for k in range(levels)]
    bid_levels = [(_clamp(bid - 0.01 * k), depth) for k in range(levels)]
    return Book(yes_bid=bid, yes_ask=ask, yes_ask_levels=ask_levels, yes_bid_levels=bid_levels)


@dataclass
class SynthData:
    frames: list[Frame]
    refs: list[MarketRef]
    curated_groups: list[MarketGroup]


def generate(*, seed: int = 7, n_equiv: int = 12, n_part: int = 8, steps: int = 30,
             spread: float = 0.03, depth: int = 300, bias0: float = 0.06,
             decay: float = 0.88) -> SynthData:
    rng = random.Random(seed)

    # --- define the latent events ---
    equiv = []   # (idx, p_true, outcome, refA, refB)
    for i in range(n_equiv):
        p = rng.uniform(0.25, 0.75)
        outcome = 1 if rng.random() < p else 0
        title = f"Will event EQ{i} occur"
        rA = MarketRef("kalshi", f"EQ{i}-K", title, f"evk{i}", "Yes")
        rB = MarketRef("polymarket", f"EQ{i}-P", title, f"evp{i}", "Yes")
        equiv.append((i, p, outcome, rA, rB))

    partitions = []  # (idx, probs[], winner, refs[])
    for j in range(n_part):
        k = rng.choice([3, 4])
        raw = [rng.uniform(0.1, 1.0) for _ in range(k)]
        s = sum(raw)
        probs = [x / s for x in raw]
        winner = rng.choices(range(k), weights=probs)[0]
        refs = [MarketRef("kalshi", f"PART{j}-{o}", f"PART{j} outcome {o}", f"part{j}", "Yes")
                for o in range(k)]
        partitions.append((j, probs, winner, refs))

    all_refs: list[MarketRef] = []
    for _, _, _, rA, rB in equiv:
        all_refs += [rA, rB]
    for _, _, _, refs in partitions:
        all_refs += refs

    # --- build frames over time ---
    frames: list[Frame] = []
    for t in range(steps):
        d = decay ** t
        ts = BASE_TS + t
        snaps: dict[str, Snapshot] = {}
        last = t == steps - 1

        for i, p, outcome, rA, rB in equiv:
            # A quotes below fair, B above -> crossed early -> pair lock; converge over t.
            midA = _clamp(p - bias0 * d + rng.uniform(-0.005, 0.005))
            midB = _clamp(p + bias0 * d + rng.uniform(-0.005, 0.005))
            snaps[rA.key] = Snapshot(rA, _book(midA, spread, depth), ts,
                                     settle=float(outcome) if last else None)
            snaps[rB.key] = Snapshot(rB, _book(midB, spread, depth), ts,
                                     settle=float(outcome) if last else None)

        for j, probs, winner, refs in partitions:
            # under-round early: scale every ask down so Σask < 1, decaying to fair.
            u = 0.10 * d
            for o, ref in enumerate(refs):
                mid = _clamp(probs[o] * (1 - u) + rng.uniform(-0.004, 0.004))
                settle = (1.0 if o == winner else 0.0) if last else None
                snaps[ref.key] = Snapshot(ref, _book(mid, spread, depth), ts, settle=settle)

        frames.append(Frame(ts=ts, snaps=snaps))

    # --- a curated groups list matching the equivalence duplicates ---
    curated_groups = [
        MarketGroup(
            key=f"synth-eq-{i}",
            members=[GroupMember("kalshi", f"EQ{i}-K", 1), GroupMember("polymarket", f"EQ{i}-P", 1)],
            kind="equivalence", trust=1.0, matcher="curated",
        )
        for i, _, _, _, _ in equiv
    ]
    return SynthData(frames=frames, refs=all_refs, curated_groups=curated_groups)


def write_curated_yaml(groups: list[MarketGroup], path: str | Path) -> Path:
    """Persist synthetic curated groups so CuratedMatcher can load them by path."""
    import yaml
    doc = {"groups": [
        {"key": g.key, "kind": g.kind, "trust": g.trust,
         "members": [{"venue": m.venue, "market_id": m.market_id, "polarity": m.polarity}
                     for m in g.members]}
        for g in groups
    ]}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        yaml.safe_dump(doc, f)
    return p
