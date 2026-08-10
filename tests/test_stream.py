"""Book cache + Polymarket WS message parsing (real message shapes)."""
import json

from predarb.common.types import Book
from predarb.stream.cache import BookCache
from predarb.stream.polymarket_ws import PolymarketStream


def test_cache_fires_callback_only_on_change():
    cache = BookCache()
    seen = []
    cache.on_update(lambda v, m, b, t: seen.append((m, b.yes_ask)))
    cache.update("kalshi", "A", Book(yes_bid=0.4, yes_ask=0.42), 1.0)
    cache.update("kalshi", "A", Book(yes_bid=0.4, yes_ask=0.42), 1.1)   # unchanged top
    cache.update("kalshi", "A", Book(yes_bid=0.4, yes_ask=0.43), 1.2)   # changed
    assert len(seen) == 2   # first + change, not the duplicate


def test_polymarket_price_change_updates_top():
    cache = BookCache()
    s = PolymarketStream(["TOKEN1"], cache)
    msg = json.dumps({"event_type": "price_change", "price_changes": [
        {"asset_id": "TOKEN1", "best_bid": "0.28", "best_ask": "0.29"}]})
    s._on_message(None, msg)
    book, _ = cache.get("polymarket:TOKEN1")
    assert book.yes_bid == 0.28 and book.yes_ask == 0.29


def test_polymarket_book_snapshot_parsed():
    cache = BookCache()
    s = PolymarketStream(["TOKEN1"], cache)
    msg = json.dumps({"event_type": "book", "asset_id": "TOKEN1",
                      "bids": [{"price": "0.30", "size": "100"}, {"price": "0.29", "size": "50"}],
                      "asks": [{"price": "0.33", "size": "80"}, {"price": "0.34", "size": "20"}]})
    s._on_message(None, msg)
    book, _ = cache.get("polymarket:TOKEN1")
    assert book.yes_bid == 0.30 and book.yes_ask == 0.33
    assert book.yes_ask_levels[0] == (0.33, 80)
