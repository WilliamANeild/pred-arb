#!/usr/bin/env python3
"""Generate the RSA key pair for Polymarket US (QCX) onboarding.

Polymarket US uses Private-Key-JWT auth (RS256): you generate an RSA key pair,
register the PUBLIC key during onboarding, and receive a Client ID. This writes the
private key to secrets/ (gitignored) and prints the public key to register.

  python scripts/gen_polymarket_us_key.py
"""
import _bootstrap  # noqa: F401

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from predarb.common.config import REPO_ROOT


def main():
    secrets = REPO_ROOT / "secrets"
    secrets.mkdir(exist_ok=True)
    priv_path = secrets / "polymarket_us_private_key.pem"
    pub_path = secrets / "polymarket_us_public_key.pem"

    if priv_path.exists():
        print(f"private key already exists at {priv_path} — refusing to overwrite.")
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv_path.write_bytes(priv_pem)
    pub_path.write_bytes(pub_pem)
    priv_path.chmod(0o600)

    print(f"private key -> {priv_path}  (gitignored; keep secret)")
    print(f"public  key -> {pub_path}\n")
    print("Register THIS public key during Polymarket US onboarding:\n")
    print(pub_pem.decode())
    print("Then set POLYMARKET_US_CLIENT_ID (from onboarding) and "
          "POLYMARKET_US_PRIVATE_KEY_PATH in .env.")


if __name__ == "__main__":
    main()
