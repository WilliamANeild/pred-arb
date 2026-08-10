#!/usr/bin/env python3
"""Emergency stop. Writes data/KILL, which blocks ALL order placement (paper or
live) instantly, checked before every order.

  python scripts/panic.py            # engage
  python scripts/panic.py --clear    # release
"""
import argparse

import _bootstrap  # noqa: F401

from predarb.common.config import SafetyConfig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clear", action="store_true", help="remove the kill file")
    args = ap.parse_args()

    kill = SafetyConfig().kill_file
    if args.clear:
        if kill.exists():
            kill.unlink()
            print(f"released: removed {kill}")
        else:
            print("no kill file present")
        return

    kill.parent.mkdir(parents=True, exist_ok=True)
    kill.touch()
    print(f"KILL ENGAGED: {kill}\nAll order placement is now blocked. Run with --clear to release.")


if __name__ == "__main__":
    main()
