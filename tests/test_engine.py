"""Live engine wiring: one cycle over a fake venue should detect and paper-fill a
partition under-round lock, entirely offline."""
import time

from predarb.common.types import Book, MarketRef, Snapshot
from predarb.engine.live import LiveEngine
from predarb.venues.base import VenueAdapter


class FakeVenue(VenueAdapter):
    name = "fake"
    env = "demo"
    market_type = "orderbook"
    executable = True

    def list_markets(self, **_):
        return [MarketRef("fake", f"O{o}", f"outcome {o}", "EVENT1", "Yes") for o in range(3)]

    def get_snapshot(self, ref):
        # three outcomes each ~0.30 -> asks sum < 1 -> riskless under-round lock
        mid = 0.30
        book = Book(yes_bid=mid - 0.005, yes_ask=mid + 0.005,
                    yes_ask_levels=[(mid + 0.005, 500)], yes_bid_levels=[(mid - 0.005, 500)])
        return Snapshot(ref, book, ts=time.time())


def test_engine_fills_paper_lock_one_cycle():
    engine = LiveEngine({"fake": FakeVenue()}, matcher="intraevent", profile="both")
    rep = engine.run(cycles=1, interval_s=0)
    assert rep.cycles == 1
    assert rep.filled >= 1          # the under-round lock was paper-filled
    assert rep.deployed_usd > 0
