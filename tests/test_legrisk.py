"""Leg-risk executor: the cross-venue safeguard. Uses a mock backend so we can
force partial fills and drift and assert the unwind behavior."""
import time

from predarb.common.config import SafetyConfig, load_params
from predarb.common.types import Leg, Opportunity, Snapshot, MarketRef, Book
from predarb.execute.legrisk import ExecutionBackend, LegFill, LegRiskExecutor
from predarb.execute.safety import GateState, SafetyGate


def _opp(legs=None):
    legs = legs or [Leg("kalshi", "A", "yes", 0.40, 20), Leg("polymarket", "B", "no", 0.55, 20)]
    return Opportunity(group_key="g", kind="dutch_book", legs=legs, edge=0.05,
                       consensus=0.5, dispersion=0.1, trust=1.0, matcher="curated")


def _snaps():
    def s(v, mid):
        ref = MarketRef(v, "X")
        b = Book(yes_bid=mid - 0.01, yes_ask=mid + 0.01,
                 yes_ask_levels=[(mid + 0.01, 500)], yes_bid_levels=[(mid - 0.01, 500)])
        return Snapshot(ref, b, ts=time.time())
    return {"kalshi:A": s("kalshi", 0.40), "polymarket:B": s("polymarket", 0.55)}


class MockBackend(ExecutionBackend):
    name = "mock"

    def __init__(self, script):
        # script: list of (filled, avg_price) per place() call, in call order
        self.script = list(script)
        self.placed, self.unwound = [], []

    def place(self, leg, qty, snaps):
        filled, avg = self.script.pop(0)
        f = LegFill(leg, filled, avg, filled * avg)
        self.placed.append(f)
        return f

    def unwind(self, fill, snaps):
        self.unwound.append(fill)
        return fill.cost_usd * 0.98   # recover most; small unwind slippage


def _exec(backend, **poverride):
    params = load_params()
    params.update(poverride)
    gate = SafetyGate(SafetyConfig(), GateState())
    return LegRiskExecutor(gate, backend, params,
                           executable_venues={"kalshi", "polymarket"})


def test_both_legs_fill_success():
    b = MockBackend([(20, 0.40), (20, 0.55)])
    rep = _exec(b).execute(_opp(), 20, _snaps())
    assert rep.success and len(rep.fills) == 2 and not b.unwound


def test_second_leg_partial_unwinds_first():
    b = MockBackend([(20, 0.40), (5, 0.55)])   # leg 2 only 5/20
    rep = _exec(b, leg_order="as_is").execute(_opp(), 20, _snaps())
    assert not rep.success
    assert len(b.unwound) == 1               # the first (filled) leg was unwound
    assert "partial" in rep.note


def test_leg_drift_aborts_and_unwinds():
    b = MockBackend([(20, 0.40), (20, 0.62)])  # leg 2 filled 0.07 worse than 0.55 quote
    rep = _exec(b, leg_order="as_is", max_leg_drift=0.02).execute(_opp(), 20, _snaps())
    assert not rep.success and "drift" in rep.note
    assert len(b.unwound) >= 1


def test_unwind_disabled_leaves_legs_open_but_flags_it():
    b = MockBackend([(20, 0.40), (0, 0.0)])
    rep = _exec(b, leg_order="as_is", unwind_on_fail=False).execute(_opp(), 20, _snaps())
    assert not rep.success and not b.unwound and "unwind disabled" in rep.note


def test_thin_first_ordering():
    # give leg B a thinner book so thin_first executes B before A
    snaps = _snaps()
    snaps["polymarket:B"].book.yes_bid_levels = [(0.54, 3)]  # NO-ask ladder derives from this
    b = MockBackend([(20, 0.55), (20, 0.40)])   # if B first, its script entry (0.55) is used first
    rep = _exec(b).execute(_opp(), 20, snaps)
    assert rep.success
    assert b.placed[0].leg.market_id == "B"     # thinnest leg went first
