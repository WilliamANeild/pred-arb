"""Polymarket US (QCX) REST client — Private-Key-JWT (RS256) auth.

Flow (docs.polymarket.us): sign a short-lived JWT assertion with your RSA private
key → POST it (grant_type=client_credentials) to the token endpoint → get a ~180s
access token → send it as `Authorization: Bearer` on market-data calls.

`token_url` and `audience` are environment-specific and provided during onboarding;
put them (plus the Client ID) in .env. Market-data reads need the registered key +
client_id but NOT KYC.
"""
from __future__ import annotations

import base64
import json
import time
import uuid
from pathlib import Path

import requests

from ..common.config import PolymarketUSConfig, polymarket_us as default_cfg
from ..common.logenv import get_logger

log = get_logger("venues.polymarket_us")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _load_private_key(path: str):
    from cryptography.hazmat.primitives import serialization
    with open(Path(path).expanduser(), "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def _rs256_jwt(claims: dict, private_key) -> str:
    """Minimal RS256 JWT (RSASSA-PKCS1-v1_5 + SHA256) — avoids a PyJWT dependency."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    header = {"alg": "RS256", "typ": "JWT"}
    signing_input = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(claims).encode())}"
    sig = private_key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64url(sig)}"


class PolymarketUSError(Exception):
    pass


class PolymarketUSClient:
    def __init__(self, cfg: PolymarketUSConfig | None = None, session: requests.Session | None = None):
        self.cfg = cfg or default_cfg
        self.session = session or requests.Session()
        self._pk = None
        self._token = None
        self._token_exp = 0.0
        if Path(self.cfg.private_key_path).expanduser().exists():
            try:
                self._pk = _load_private_key(self.cfg.private_key_path)
            except Exception as e:  # noqa: BLE001
                log.warning("could not load Polymarket US private key: %s", e)

    # ---- auth -----------------------------------------------------------
    def _assertion(self, now: float | None = None) -> str:
        now = int(now or time.time())
        claims = {
            "iss": self.cfg.client_id, "sub": self.cfg.client_id,
            "aud": self.cfg.audience, "iat": now, "exp": now + 180,
            "jti": str(uuid.uuid4()),
        }
        return _rs256_jwt(claims, self._pk)

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_exp - 15:
            return self._token
        if not (self._pk and self.cfg.client_id and self.cfg.token_url and self.cfg.audience):
            raise PolymarketUSError("Polymarket US not onboarded: need client_id, token_url, "
                                    "audience, and a registered RSA key")
        r = self.session.post(self.cfg.token_url, data={
            "grant_type": "client_credentials",
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": self._assertion(),
        }, timeout=20)
        if r.status_code != 200:
            raise PolymarketUSError(f"token exchange failed HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        self._token = data["access_token"]
        self._token_exp = time.time() + int(data.get("expires_in", 180))
        return self._token

    def _get(self, path: str, params: dict | None = None) -> dict:
        r = self.session.get(self.cfg.base_url + path,
                             headers={"Authorization": f"Bearer {self._access_token()}"},
                             params=params, timeout=20)
        if r.status_code != 200:
            raise PolymarketUSError(f"GET {path} HTTP {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else {}

    # ---- market data ----------------------------------------------------
    def list_instruments(self, *, sport: str | None = None, league: str | None = None) -> list[dict]:
        params = {k: v for k, v in {"sport": sport, "league": league}.items() if v}
        data = self._get("/v1/instruments", params=params)
        return data.get("instruments", data if isinstance(data, list) else [])

    def get_bbo(self, symbol: str) -> dict:
        return self._get(f"/v1/orderbook/{symbol}/bbo")

    def get_orderbook(self, symbol: str) -> dict:
        return self._get(f"/v1/orderbook/{symbol}")
