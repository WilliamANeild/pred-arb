#!/usr/bin/env python3
"""Analyze a recorded tick session for cross-venue dislocations.

  python scripts/analyze_dislocation.py data/ticks/mlb_1234.jsonl
"""
import argparse
import json

import _bootstrap  # noqa: F401

from predarb.common.config import DATA_DIR
from predarb.research.dislocation import analyze, format_stats, load_ticks
from predarb.research.pairs import Pair


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticks", help="path to data/ticks/<session>.jsonl")
    ap.add_argument("--pairs", default=str(DATA_DIR / "mlb_pairs.json"))
    args = ap.parse_args()

    ticks = load_ticks(args.ticks)
    pairs = [Pair.from_dict(d) for d in json.load(open(args.pairs))]
    print(f"{len(ticks)} ticks, {len(pairs)} pairs\n")

    results = []
    for p in pairs:
        st = analyze(ticks, p)
        if st.n_both == 0:
            continue
        results.append(st)
        print(format_stats(st))
        print()

    capturable = [s for s in results if s.n_episodes and s.median_episode_s >= 1.0]
    print("=" * 50)
    print(f"pairs with both-venue data: {len(results)}")
    print(f"pairs with persistent (>=1s) dislocations: {len(capturable)}")
    if not capturable:
        print("-> No capturable edge observed in this session. Do NOT risk money on it.")


if __name__ == "__main__":
    main()
