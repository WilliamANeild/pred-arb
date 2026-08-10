"""Configuration + safety flags. Loads .env and config/params.yaml.

Live trading is gated by ALL of SafetyConfig's switches. Every risk cap is
env-configurable (edit .env, no code change). Defaults are deliberately tiny.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv optional; env vars may be set externally
    pass

try:
    import yaml
except ImportError:
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
CONFIG_DIR = REPO_ROOT / "config"

KALSHI_HOSTS = {
    "demo": "https://demo-api.kalshi.co/trade-api/v2",
    "prod": "https://api.elections.kalshi.com/trade-api/v2",
}
# Polymarket public data (Gamma) + order book (CLOB). Reads need no auth.
POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB = "https://clob.polymarket.com"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _as_bool(v: str) -> bool:
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _f(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(float(_env(name, str(default))))
    except ValueError:
        return default


@dataclass
class KalshiConfig:
    env: str = field(default_factory=lambda: _env("KALSHI_ENV", "demo"))
    key_id: str = field(default_factory=lambda: _env("KALSHI_KEY_ID"))
    private_key_path: str = field(
        default_factory=lambda: _env("KALSHI_PRIVATE_KEY_PATH", "./secrets/kalshi_private_key.pem")
    )

    @property
    def base_url(self) -> str:
        return KALSHI_HOSTS.get(self.env, KALSHI_HOSTS["demo"])

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    def has_credentials(self) -> bool:
        return bool(self.key_id) and Path(self.private_key_path).expanduser().exists()


@dataclass
class PolymarketConfig:
    enabled: bool = field(default_factory=lambda: _as_bool(_env("POLYMARKET_ENABLED", "true")))
    api_key: str = field(default_factory=lambda: _env("POLYMARKET_API_KEY"))
    api_secret: str = field(default_factory=lambda: _env("POLYMARKET_API_SECRET"))
    api_passphrase: str = field(default_factory=lambda: _env("POLYMARKET_API_PASSPHRASE"))
    gamma_url: str = POLYMARKET_GAMMA
    clob_url: str = POLYMARKET_CLOB

    def has_credentials(self) -> bool:
        return bool(self.api_key and self.api_secret and self.api_passphrase)


@dataclass
class SafetyConfig:
    """Live-trading is gated by ALL of these. Missing any -> paper only."""
    allow_live_trading: bool = field(default_factory=lambda: _as_bool(_env("ALLOW_LIVE_TRADING", "false")))
    kill_switch: bool = field(default_factory=lambda: _as_bool(_env("KILL_SWITCH", "false")))

    bankroll_usd: float = field(default_factory=lambda: _f("BANKROLL_USD", 100.0))

    # Hard risk caps (dollars / contracts).
    max_contracts_per_order: int = field(default_factory=lambda: _i("MAX_CONTRACTS_PER_ORDER", 20))
    max_notional_per_market_usd: float = field(default_factory=lambda: _f("MAX_NOTIONAL_PER_MARKET_USD", 25.0))
    max_notional_per_group_usd: float = field(default_factory=lambda: _f("MAX_NOTIONAL_PER_GROUP_USD", 40.0))
    max_total_notional_usd: float = field(default_factory=lambda: _f("MAX_TOTAL_NOTIONAL_USD", 100.0))
    daily_loss_limit_usd: float = field(default_factory=lambda: _f("DAILY_LOSS_LIMIT_USD", 50.0))

    # Circuit breakers / runaway protection.
    max_price_cents: int = field(default_factory=lambda: _i("MAX_PRICE_CENTS", 97))
    max_orders_per_session: int = field(default_factory=lambda: _i("MAX_ORDERS_PER_SESSION", 25))
    max_consecutive_errors: int = field(default_factory=lambda: _i("MAX_CONSECUTIVE_ERRORS", 3))
    feed_staleness_seconds: int = field(default_factory=lambda: _i("FEED_STALENESS_SECONDS", 120))

    # Arbitrage strategy guards.
    live_riskless_only: bool = field(default_factory=lambda: _as_bool(_env("LIVE_RISKLESS_ONLY", "true")))
    min_edge_live: float = field(default_factory=lambda: _f("MIN_EDGE_LIVE", 0.03))
    min_consensus: float = field(default_factory=lambda: _f("MIN_CONSENSUS", 0.15))
    max_consensus: float = field(default_factory=lambda: _f("MAX_CONSENSUS", 0.85))
    deviation_threshold: float = field(default_factory=lambda: _f("DEVIATION_THRESHOLD", 0.05))
    min_depth_contracts: int = field(default_factory=lambda: _i("MIN_DEPTH_CONTRACTS", 10))
    max_spread: float = field(default_factory=lambda: _f("MAX_SPREAD", 0.10))
    cluster_trust_floor: float = field(default_factory=lambda: _f("CLUSTER_TRUST_FLOOR", 0.80))

    @property
    def kill_file(self) -> Path:
        return DATA_DIR / "KILL"

    def kill_engaged(self) -> bool:
        """Halt if the env flag is set OR a data/KILL file exists (touch it to stop
        the bot instantly without editing .env while it runs)."""
        return self.kill_switch or self.kill_file.exists()

    def live_allowed(self, venue_env: str, run_live_flag: bool) -> bool:
        """Real orders require prod env AND global allow AND per-run flag AND no kill."""
        return (
            self.allow_live_trading
            and venue_env == "prod"
            and run_live_flag
            and not self.kill_engaged()
        )


def load_params() -> dict:
    """Strategy params from config/params.yaml (falls back to built-in defaults)."""
    defaults = {
        "min_consensus": 0.15,
        "max_consensus": 0.85,
        "deviation_threshold": 0.05,
        "close_deviation": 0.01,
        "dispersion_min": 0.03,
        "weight_by_liquidity": True,
        "min_depth_contracts": 10,
        "max_spread": 0.10,
        "phantom_haircut": 0.5,
        "kalshi_fee_rate": 0.07,
        "polymarket_fee_rate": 0.0,
        "riskless_min_edge": 0.01,
        "relval_min_edge": 0.04,
        "kelly_fraction": 0.20,
        "confidence_floor": 0.10,
        "cluster_trust": 0.60,
    }
    path = CONFIG_DIR / "params.yaml"
    if yaml and path.exists():
        with open(path) as f:
            user = yaml.safe_load(f) or {}
        defaults.update(user)
    return defaults


kalshi = KalshiConfig()
polymarket = PolymarketConfig()
safety = SafetyConfig()
