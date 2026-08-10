"""Polymarket CLOB WebSocket client (public, no auth).

Message shapes confirmed live:
  book         -> {event_type:"book", asset_id, bids:[{price,size}], asks:[{price,size}]}
  price_change -> {event_type:"price_change", price_changes:[{asset_id, best_bid, best_ask, ...}]}

We subscribe to YES-outcome token ids and maintain each token's top-of-book in the
shared BookCache. `price_change` carries best_bid/best_ask directly, so top-of-book
stays live tick-by-tick.
"""
from __future__ import annotations

import json
import threading
import time

from ..common.config import POLYMARKET_WS
from ..common.logenv import get_logger
from ..common.types import Book
from .cache import BookCache

log = get_logger("stream.polymarket")


def _levels(rows):
    out = []
    for r in rows or []:
        try:
            out.append((float(r["price"]), int(float(r["size"]))))
        except (KeyError, TypeError, ValueError):
            pass
    return out


class PolymarketStream:
    def __init__(self, token_ids: list[str], cache: BookCache):
        self.token_ids = [str(t) for t in token_ids]
        self.cache = cache
        self._ws = None
        self._thread = None
        self._stop = False
        # remember last best bid/ask per token so a one-sided price_change still yields a book
        self._last: dict[str, list] = {t: [None, None] for t in self.token_ids}

    def _apply(self, asset_id: str, bid, ask, ask_levels=None, bid_levels=None):
        last = self._last.setdefault(asset_id, [None, None])
        if bid is not None:
            last[0] = float(bid)
        if ask is not None:
            last[1] = float(ask)
        book = Book(yes_bid=last[0], yes_ask=last[1],
                    yes_ask_levels=ask_levels or [], yes_bid_levels=bid_levels or [])
        self.cache.update("polymarket", asset_id, book, time.time())

    def _on_message(self, _ws, raw):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return
        for ev in (obj if isinstance(obj, list) else [obj]):
            et = ev.get("event_type")
            if et == "book":
                aid = ev.get("asset_id")
                asks = sorted(_levels(ev.get("asks") or ev.get("sells")), key=lambda x: x[0])
                bids = sorted(_levels(ev.get("bids") or ev.get("buys")), key=lambda x: -x[0])
                self._apply(aid, bids[0][0] if bids else None, asks[0][0] if asks else None,
                            ask_levels=asks, bid_levels=bids)
            elif et == "price_change":
                for pc in ev.get("price_changes", []):
                    self._apply(pc.get("asset_id"), pc.get("best_bid"), pc.get("best_ask"))

    def _on_open(self, ws):
        ws.send(json.dumps({"assets_ids": self.token_ids, "type": "market"}))
        log.info("subscribed to %d polymarket tokens", len(self.token_ids))

    def start(self):
        import websocket
        def run():
            while not self._stop:
                try:
                    self._ws = websocket.WebSocketApp(
                        POLYMARKET_WS, on_open=self._on_open, on_message=self._on_message)
                    self._ws.run_forever(ping_interval=10, ping_timeout=5)
                except Exception as e:  # noqa: BLE001 — reconnect on any drop
                    log.warning("polymarket ws error: %s", e)
                if not self._stop:
                    time.sleep(1.0)
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop = True
        try:
            if self._ws:
                self._ws.close()
        except Exception:  # noqa: BLE001
            pass
