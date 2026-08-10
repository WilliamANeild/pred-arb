#!/usr/bin/env python3
"""Run the matcher x profile grid backtest.

  python scripts/backtest.py --synth          # deterministic, no network/keys
  python scripts/backtest.py                  # on recorded data/snapshots.jsonl
"""
import argparse

import _bootstrap  # noqa: F401

from predarb.backtest.grid import format_grid, run_grid
from predarb.backtest.metrics import format_report
from predarb.backtest.synth import generate
from predarb.common.config import SafetyConfig, load_params
from predarb.recorder.store import SnapshotStore


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synth", action="store_true", help="use synthetic data")
    ap.add_argument("--min-trades", type=int, default=None,
                    help="go-live gate sample floor (default 5 synth / 30 real)")
    args = ap.parse_args()

    params = load_params()
    safety = SafetyConfig()

    if args.synth:
        data = generate()
        frames, refs, curated = data.frames, data.refs, data.curated_groups
        min_trades = args.min_trades or 5
        print(f"synthetic timeline: {len(frames)} frames, {len(refs)} markets\n")
    else:
        frames = SnapshotStore().load_frames()
        if not frames:
            raise SystemExit("no recorded data at data/snapshots.jsonl — run scripts/record.py "
                             "or use --synth")
        refs = list({s.ref.key: s.ref for fr in frames for s in fr.snaps.values()}.values())
        curated = None
        min_trades = args.min_trades or 30
        print(f"recorded timeline: {len(frames)} frames, {len(refs)} markets\n")

    cells = run_grid(frames, refs, params, safety, curated_groups=curated, min_trades=min_trades)
    print(format_grid(cells))
    print("\n=== best cell ===")
    best = cells[0]
    print(f"{best.matcher} x {best.profile}")
    print(format_report(best.metrics))
    for r in best.gate_reasons:
        print(f"  {r}")


if __name__ == "__main__":
    main()
