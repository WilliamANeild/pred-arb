"""Kalshi REST client with RSA-PSS request signing.

Lifted from a prior project of the author's. Reads (markets, orderbook,
candlesticks, trades) are public. Writes (orders, balance, positions) require a
signed key. demo/prod switched via config.

Signing: base64( RSA-PSS-SHA256( timestamp_ms + METHOD + path ) ) with MGF1-SHA256
and salt length = digest length (32).
"""
from __future__ import annotations

import base64
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from ..common.config import KalshiConfig, kalshi as default_cfg
from ..common.logenv import get_logger

log = get_logger("venues.kalshi")


class KalshiAPIError(Exception):
    """A deterministic 4xx from Kalshi (rejected order, bad price, closed market,
    insufficient balance, position limit). Carries the status code + reason."""
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"HTTP {status}: {message}")


def _load_private_key(path: str):
    from cryptography.hazmat.primitives import serialization
    p = Path(path).expanduser()
    with open(p, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def _sign(private_key, message: str) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    sig = private_key.sign(
        message.encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(sig).decode()


@dataclass
class Orderbook:
    ticker: str
    yes_bids: list[tuple[int, int]]   # (price_cents, qty) — buyers of YES
    no_bids: list[tuple[int, int]]    # (price_cents, qty) — buyers of NO

    @property
    def best_yes_ask(self) -> tuple[int, int] | None:
        """Cheapest YES you can BUY = 100 - best NO bid."""
        if not self.no_bids:
            return None
        price, qty = max(self.no_bids, key=lambda x: x[0])
        return (100 - price, qty)

    @property
    def best_yes_bid(self) -> tuple[int, int] | None:
        """Highest YES you can SELL to."""
        if not self.yes_bids:
            return None
        return max(self.yes_bids, key=lambda x: x[0])

    def yes_ask_levels(self) -> list[tuple[int, int]]:
        """YES ask ladder (ascending price) synthesized from NO bids."""
        return sorted(((100 - p, q) for p, q in self.no_bids), key=lambda x: x[0])

    def yes_bid_levels(self) -> list[tuple[int, int]]:
        return sorted(self.yes_bids, key=lambda x: -x[0])


class KalshiClient:
    def __init__(self, cfg: KalshiConfig | None = None, session: requests.Session | None = None):
        self.cfg = cfg or default_cfg
        self.session = session or requests.Session()
        self._pk = None
        self._min_interval = 0.12   # pace requests to stay under read rate limits
        self._last_req = 0.0
        if self.cfg.has_credentials():
            try:
                self._pk = _load_private_key(self.cfg.private_key_path)
            except Exception as e:  # noqa: BLE001
                log.warning("could not load private key: %s (reads still work)", e)

    # ---- signing ---------------------------------------------------------
    def _headers(self, method: str, path: str) -> dict[str, str]:
        if not self._pk or not self.cfg.key_id:
            return {}
        ts = str(int(time.time() * 1000))
        msg = ts + method.upper() + path.split("?")[0]
        return {
            "KALSHI-ACCESS-KEY": self.cfg.key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": _sign(self._pk, msg),
        }

    def _request(self, method: str, path: str, *, params=None, body=None, signed=False) -> dict:
        url = self.cfg.base_url + path
        headers = {"Content-Type": "application/json"}
        if signed:
            # Kalshi signs the path INCLUDING the /trade-api/v2 prefix.
            sign_path = "/trade-api/v2" + path
            headers.update(self._headers(method, sign_path))
            if not headers.get("KALSHI-ACCESS-KEY"):
                raise RuntimeError("signed request requires Kalshi credentials (set KALSHI_KEY_ID / key PEM)")
        for attempt in range(5):
            dt = time.time() - self._last_req
            if dt < self._min_interval:
                time.sleep(self._min_interval - dt)
            try:
                r = self.session.request(method, url, params=params, json=body, headers=headers, timeout=20)
                self._last_req = time.time()
                if r.status_code == 429:
                    time.sleep(0.75 * (attempt + 1))
                    continue
                # 4xx = deterministic client error. Do NOT retry; surface the reason.
                if 400 <= r.status_code < 500:
                    body_txt = ""
                    try:
                        body_txt = r.json().get("error", {}).get("message") or r.text
                    except Exception:  # noqa: BLE001
                        body_txt = r.text
                    raise KalshiAPIError(r.status_code, str(body_txt)[:300])
                r.raise_for_status()
                return r.json() if r.content else {}
            except KalshiAPIError:
                raise
            except requests.RequestException as e:
                log.warning("%s %s failed (attempt %d): %s", method, path, attempt + 1, e)
                time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"{method} {path} failed after retries")

    # ---- market data (public) -------------------------------------------
    def get_markets(self, *, series_ticker=None, event_ticker=None, status=None,
                    tickers=None, limit=100, cursor=None) -> dict:
        params = {k: v for k, v in {
            "series_ticker": series_ticker, "event_ticker": event_ticker,
            "status": status, "tickers": tickers, "limit": limit, "cursor": cursor,
        }.items() if v is not None}
        return self._request("GET", "/markets", params=params)

    def iter_all_markets(self, max_pages: int = 20, **kw) -> list[dict]:
        out, cursor, pages = [], None, 0
        while pages < max_pages:
            page = self.get_markets(cursor=cursor, **kw)
            out.extend(page.get("markets", []))
            cursor = page.get("cursor")
            pages += 1
            if not cursor:
                break
        return out

    def get_market(self, ticker: str) -> dict:
        return self._request("GET", f"/markets/{ticker}").get("market", {})

    def get_events(self, *, series_ticker=None, status=None, with_nested_markets=False, limit=100) -> dict:
        params = {k: v for k, v in {
            "series_ticker": series_ticker, "status": status,
            "with_nested_markets": with_nested_markets, "limit": limit,
        }.items() if v is not None}
        return self._request("GET", "/events", params=params)

    def get_orderbook(self, ticker: str, depth: int = 0) -> Orderbook:
        raw = self._request("GET", f"/markets/{ticker}/orderbook", params={"depth": depth})
        # Post-2026 API returns fixed-point levels under `orderbook_fp` with
        # `yes_dollars`/`no_dollars`; older shape used `orderbook`/`yes`/`no`.
        ob = raw.get("orderbook") or raw.get("orderbook_fp") or {}
        yes = _normalize_levels(ob.get("yes") if ob.get("yes") is not None else ob.get("yes_dollars"))
        no = _normalize_levels(ob.get("no") if ob.get("no") is not None else ob.get("no_dollars"))
        return Orderbook(ticker=ticker, yes_bids=yes, no_bids=no)

    # ---- account / orders (signed) --------------------------------------
    def get_balance(self) -> dict:
        return self._request("GET", "/portfolio/balance", signed=True)

    def create_order(self, *, ticker: str, action: str, side: str, count: int,
                     price_cents: int | None = None, client_order_id: str | None = None,
                     time_in_force: str = "good_till_canceled") -> dict:
        """Place an order via the V2 single-book endpoint.

        V2 uses a single book side: "bid" = buy YES, "ask" = sell YES = buy NO.
        We keep the (action=buy, side=yes|no, price_cents) interface and translate.
        """
        if action != "buy":
            raise ValueError("only 'buy' is supported (buy YES or buy NO)")
        if price_cents is None:
            raise ValueError("limit order requires price_cents (1-99)")
        p = price_cents / 100.0
        if side == "yes":
            book_side, price = "bid", p
        elif side == "no":
            book_side, price = "ask", 1.0 - p
        else:
            raise ValueError("side must be 'yes' or 'no'")
        body: dict[str, Any] = {
            "ticker": ticker,
            "side": book_side,
            "count": f"{float(count):.2f}",
            "price": f"{price:.4f}",
            "time_in_force": time_in_force,
            "self_trade_prevention_type": "taker_at_cross",
            "client_order_id": client_order_id or str(uuid.uuid4()),
        }
        return self._request("POST", "/portfolio/events/orders", body=body, signed=True)

    def cancel_order(self, order_id: str) -> dict:
        return self._request("DELETE", f"/portfolio/events/orders/{order_id}", signed=True)


def _normalize_levels(levels) -> list[tuple[int, int]]:
    """Kalshi orderbook levels are [price, qty]; post-2026 may be dollar strings.
    Normalize to (price_cents:int, qty:int)."""
    out: list[tuple[int, int]] = []
    for lvl in levels or []:
        try:
            p, q = lvl[0], lvl[1]
            pc = round(float(p) * 100) if isinstance(p, str) and "." in p else int(round(float(p)))
            qn = int(round(float(q)))
            out.append((pc, qn))
        except (TypeError, ValueError, IndexError):
            continue
    return out
