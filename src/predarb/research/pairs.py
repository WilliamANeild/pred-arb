"""A cross-venue pair we stream and measure: two markets asserted to resolve
identically, with the polarity that aligns their YES sides."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Pair:
    label: str
    kalshi_ticker: str
    poly_token: str
    kind: str                 # "total" | "moneyline"
    line: float | None = None
    polarity: int = 1         # +1: polymarket YES == kalshi YES == event YES
    fee_rate: float = 0.07    # kalshi taker-fee coefficient

    @property
    def kalshi_key(self) -> str:
        return f"kalshi:{self.kalshi_ticker}"

    @property
    def poly_key(self) -> str:
        return f"polymarket:{self.poly_token}"

    def to_dict(self) -> dict:
        return {"label": self.label, "kalshi_ticker": self.kalshi_ticker,
                "poly_token": self.poly_token, "kind": self.kind, "line": self.line,
                "polarity": self.polarity, "fee_rate": self.fee_rate}

    @staticmethod
    def from_dict(d: dict) -> "Pair":
        return Pair(label=d["label"], kalshi_ticker=d["kalshi_ticker"],
                    poly_token=d["poly_token"], kind=d.get("kind", "total"),
                    line=d.get("line"), polarity=d.get("polarity", 1),
                    fee_rate=d.get("fee_rate", 0.07))
