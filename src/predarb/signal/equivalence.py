"""Structured equivalence guard — the antidote to false cross-venue matches.

Title similarity alone is DANGEROUS: it rates "Alvarez 2+ HR in this game" and
"Alvarez most HR this season" as a match, or "Bitcoin above $62k" and "Bitcoin dip
to $62k" (opposite polarity). Those false matches are where the biggest fake
"edges" show up, so trading them loses money.

This module extracts the structured facts that actually determine whether two
markets resolve identically — the numeric threshold (strike/line), the direction
(above/below, over/under), and the date — and only calls two markets equivalent
when those agree. It is deliberately strict: when unsure, say NOT equivalent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_UP = ("above", "over", "more", "at least", "reach", "exceed", "greater", "+", "or above", "or more")
_DOWN = ("below", "under", "less", "dip", "fewer", "at most", "or below", "or less", "down to")

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


@dataclass
class MarketFacts:
    numbers: set[float]
    direction: str | None      # "up" | "down" | None
    date: tuple[int, int] | None  # (month, day) if present


def _numbers(s: str) -> set[float]:
    out = set()
    for m in re.findall(r"\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", s):
        try:
            out.add(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def _direction(s: str) -> str | None:
    low = s.lower()
    up = any(w in low for w in _UP)
    down = any(w in low for w in _DOWN)
    if up and not down:
        return "up"
    if down and not up:
        return "down"
    return None


def _date(s: str) -> tuple[int, int] | None:
    low = s.lower()
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b", low)
    if m:
        return (_MONTHS[m.group(1)], int(m.group(2)))
    m = re.search(r"\b(\d{1,2})/(\d{1,2})\b", low)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return None


def extract(title: str) -> MarketFacts:
    return MarketFacts(numbers=_numbers(title), direction=_direction(title), date=_date(title))


def is_equivalent(a_title: str, b_title: str, *, num_tol: float = 0.0) -> tuple[bool, str]:
    """Strict resolve-identically check. Returns (equivalent, reason)."""
    a, b = extract(a_title), extract(b_title)

    # 1. shared numeric threshold (strike / line) — the single most important key.
    if a.numbers and b.numbers:
        shared = any(abs(x - y) <= num_tol for x in a.numbers for y in b.numbers)
        if not shared:
            return False, f"different threshold {sorted(a.numbers)} vs {sorted(b.numbers)}"
    elif a.numbers or b.numbers:
        return False, "one side has a numeric threshold, the other doesn't"

    # 2. direction must not conflict (above vs dip/below is an inversion, not a match).
    if a.direction and b.direction and a.direction != b.direction:
        return False, f"opposite direction ({a.direction} vs {b.direction})"

    # 3. dates, if both present, must match (a 2-day shift is basis risk, not a lock).
    if a.date and b.date and a.date != b.date:
        return False, f"different date {a.date} vs {b.date}"

    return True, "threshold/direction/date consistent"
