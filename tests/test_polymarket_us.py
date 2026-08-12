"""Polymarket US RS256 JWT assertion — verifiable offline, no network/creds."""
import base64
import json

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from predarb.common.config import PolymarketUSConfig
from predarb.venues.polymarket_us_client import PolymarketUSClient, _rs256_jwt


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def test_rs256_jwt_structure_and_signature():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = {"iss": "cid", "sub": "cid", "aud": "aud", "iat": 1000, "exp": 1180, "jti": "x"}
    token = _rs256_jwt(claims, key)
    header_b64, payload_b64, sig_b64 = token.split(".")

    assert json.loads(_b64url_decode(header_b64)) == {"alg": "RS256", "typ": "JWT"}
    assert json.loads(_b64url_decode(payload_b64)) == claims
    # signature verifies against the public key over "header.payload"
    key.public_key().verify(
        _b64url_decode(sig_b64), f"{header_b64}.{payload_b64}".encode(),
        padding.PKCS1v15(), hashes.SHA256())


def test_assertion_claims_use_client_id_and_expiry():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    c = PolymarketUSClient(PolymarketUSConfig(client_id="CID-123", audience="AUD"))
    c._pk = key
    token = c._assertion(now=1_000_000)
    claims = json.loads(_b64url_decode(token.split(".")[1]))
    assert claims["iss"] == "CID-123" and claims["sub"] == "CID-123"
    assert claims["aud"] == "AUD"
    assert claims["exp"] - claims["iat"] == 180   # short-lived, per docs (<=5 min)


def test_no_creds_raises_clear_error():
    c = PolymarketUSClient(PolymarketUSConfig(client_id="", token_url="", audience=""))
    c._pk = None
    import pytest
    with pytest.raises(Exception, match="not onboarded"):
        c._access_token()
