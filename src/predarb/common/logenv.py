"""Minimal structured logging helper."""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def get_logger(name: str = "predarb") -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s", "%H:%M:%S")
        )
        root = logging.getLogger("predarb")
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        _CONFIGURED = True
    return logging.getLogger(name if name.startswith("predarb") else f"predarb.{name}")
