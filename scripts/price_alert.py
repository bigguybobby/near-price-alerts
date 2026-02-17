#!/usr/bin/env python3
"""
NEAR token price alert skill for OpenClaw.

Fetches NEAR price from multiple sources (CoinGecko, Binance, Kraken, CoinCap)
with fallback, evaluates configurable alert thresholds, and outputs results
in human-readable or JSON format.
"""

import argparse
import json
import logging
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("near-price-alerts")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCES = {
    "coingecko": (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=near&vs_currencies=usd&include_24hr_change=true"
    ),
    "binance": "https://api.binance.com/api/v3/ticker/24hr?symbol=NEARUSDT",
    "kraken": "https://api.kraken.com/0/public/Ticker?pair=NEARUSD",
    "coincap": "https://api.coincap.io/v2/assets/near-protocol",
}

DEFAULT_TIMEOUT = 10
MAX_RETRIES = 3
RETRY_DELAY = 1.5  # seconds


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PriceData:
    """Normalised price data returned by any source."""

    source: str
    price_usd: float
    change_24h_pct: float
    volume_24h_usd: Optional[float] = None
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = time.time()


# ---------------------------------------------------------------------------
# Price-source fetchers
# ---------------------------------------------------------------------------

def _http_get(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Perform a GET request and return parsed JSON."""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "OpenClaw-NEAR-Alerts/2.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_coingecko() -> PriceData:
    """Fetch NEAR price from CoinGecko free API."""
    data = _http_get(SOURCES["coingecko"])
    near = data["near"]
    return PriceData(
        source="coingecko",
        price_usd=float(near["usd"]),
        change_24h_pct=float(near.get("usd_24h_change", 0.0)),
    )


def fetch_binance() -> PriceData:
    """Fetch NEAR price from Binance public ticker."""
    data = _http_get(SOURCES["binance"])
    return PriceData(
        source="binance",
        price_usd=float(data["lastPrice"]),
        change_24h_pct=float(data["priceChangePercent"]),
        volume_24h_usd=float(data["quoteVolume"]),
        high_24h=float(data["highPrice"]),
        low_24h=float(data["lowPrice"]),
    )


def fetch_kraken() -> PriceData:
    """Fetch NEAR price from Kraken public ticker."""
    data = _http_get(SOURCES["kraken"])
    pair_data = list(data["result"].values())[0]
    price = float(pair_data["c"][0])
    open_ = float(pair_data["o"])
    change_pct = ((price - open_) / open_) * 100 if open_ else 0.0
    return PriceData(
        source="kraken",
        price_usd=price,
        change_24h_pct=change_pct,
        high_24h=float(pair_data["h"][0]),
        low_24h=float(pair_data["l"][0]),
    )


def fetch_coincap() -> PriceData:
    """Fetch NEAR price from CoinCap API."""
    data = _http_get(SOURCES["coincap"])
    asset = data["data"]
    return PriceData(
        source="coincap",
        price_usd=float(asset["priceUsd"]),
        change_24h_pct=float(asset.get("changePercent24Hr", 0.0)),
        volume_24h_usd=float(asset.get("volumeUsd24Hr", 0.0) or 0.0),
    )


_FETCHERS = {
    "coingecko": fetch_coingecko,
    "binance": fetch_binance,
    "kraken": fetch_kraken,
    "coincap": fetch_coincap,
}

FETCH_ORDER = ["coingecko", "binance", "kraken", "coincap"]


def get_near_price(
    source: Optional[str] = None,
    fallback: bool = True,
    retries: int = MAX_RETRIES,
) -> PriceData:
    """
    Fetch current NEAR price, trying sources in order until one succeeds.

    Args:
        source:   Preferred source name (None = try all in default order).
        fallback: If True and the preferred source fails, try others.
        retries:  Number of retry attempts per source.

    Returns:
        PriceData with normalised price information.

    Raises:
        RuntimeError: When all sources are exhausted.
    """
    order = [source] if source else FETCH_ORDER
    if fallback and source and source in FETCH_ORDER:
        rest = [s for s in FETCH_ORDER if s != source]
        order = [source] + rest

    last_error: Exception = RuntimeError("No sources available")
    for src in order:
        fetcher = _FETCHERS.get(src)
        if not fetcher:
            logger.warning("Unknown source '%s', skipping", src)
            continue
        for attempt in range(retries):
            try:
                data = fetcher()
                logger.info("Price fetched from %s: $%.4f", src, data.price_usd)
                return data
            except Exception as exc:
                wait = RETRY_DELAY * (attempt + 1)
                logger.warning(
                    "Source %s attempt %d/%d failed: %s. Retrying in %.1fs",
                    src, attempt + 1, retries, exc, wait,
                )
                last_error = exc
                if attempt < retries - 1:
                    time.sleep(wait)
    raise RuntimeError(f"All price sources failed. Last error: {last_error}") from last_error


def aggregate_price(sources: Optional[list[str]] = None) -> dict:
    """
    Fetch price from multiple sources and return aggregated stats.

    Args:
        sources: List of source names (default: all).

    Returns:
        Dict with individual results, average, min, max.
    """
    targets = sources or FETCH_ORDER
    results = []
    errors = {}
    for src in targets:
        try:
            pd = _FETCHERS[src]()
            results.append(pd)
        except Exception as exc:
            errors[src] = str(exc)

    if not results:
        raise RuntimeError(f"All sources failed: {errors}")

    prices = [r.price_usd for r in results]
    changes = [r.change_24h_pct for r in results]
    return {
        "sources": [asdict(r) for r in results],
        "average_price_usd": sum(prices) / len(prices),
        "min_price_usd": min(prices),
        "max_price_usd": max(prices),
        "spread_pct": (max(prices) - min(prices)) / min(prices) * 100 if min(prices) else 0,
        "average_change_24h_pct": sum(changes) / len(changes),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Alert evaluation
# ---------------------------------------------------------------------------

@dataclass
class Alert:
    """A triggered alert with level and message."""

    level: str  # "INFO", "WARN", "CRITICAL"
    message: str
    triggered_value: float
    threshold: float


def check_alerts(price_data: PriceData, config: dict) -> list[Alert]:
    """
    Evaluate price against configured alert thresholds.

    Supported thresholds in config["thresholds"]:
        above         — alert if price >= value
        below         — alert if price <= value
        change_pct    — alert if |24h change| >= value
        high_24h      — alert if high >= value
        low_24h       — alert if low <= value
        spread_alert  — (aggregated) alert if source spread_pct >= value

    Args:
        price_data: Normalised price data from a fetcher.
        config:     Configuration dict (may include "thresholds" sub-key).

    Returns:
        List of triggered Alert objects.
    """
    alerts: list[Alert] = []
    thresholds = config.get("thresholds", {})

    if "above" in thresholds and price_data.price_usd >= thresholds["above"]:
        alerts.append(
            Alert(
                level="CRITICAL",
                message=(
                    f"🚀 NEAR broke above ${thresholds['above']:.2f}! "
                    f"Current: ${price_data.price_usd:.4f}"
                ),
                triggered_value=price_data.price_usd,
                threshold=thresholds["above"],
            )
        )

    if "below" in thresholds and price_data.price_usd <= thresholds["below"]:
        alerts.append(
            Alert(
                level="CRITICAL",
                message=(
                    f"🔻 NEAR dropped below ${thresholds['below']:.2f}! "
                    f"Current: ${price_data.price_usd:.4f}"
                ),
                triggered_value=price_data.price_usd,
                threshold=thresholds["below"],
            )
        )

    if "change_pct" in thresholds:
        pct = thresholds["change_pct"]
        if abs(price_data.change_24h_pct) >= pct:
            direction = "📈" if price_data.change_24h_pct > 0 else "📉"
            level = "CRITICAL" if abs(price_data.change_24h_pct) >= pct * 2 else "WARN"
            alerts.append(
                Alert(
                    level=level,
                    message=(
                        f"{direction} NEAR 24h change: {price_data.change_24h_pct:+.2f}% "
                        f"(threshold: ±{pct}%)"
                    ),
                    triggered_value=price_data.change_24h_pct,
                    threshold=pct,
                )
            )

    if "high_24h" in thresholds and price_data.high_24h is not None:
        if price_data.high_24h >= thresholds["high_24h"]:
            alerts.append(
                Alert(
                    level="WARN",
                    message=(
                        f"📊 NEAR 24h high ${price_data.high_24h:.4f} "
                        f"exceeded target ${thresholds['high_24h']:.2f}"
                    ),
                    triggered_value=price_data.high_24h,
                    threshold=thresholds["high_24h"],
                )
            )

    if "low_24h" in thresholds and price_data.low_24h is not None:
        if price_data.low_24h <= thresholds["low_24h"]:
            alerts.append(
                Alert(
                    level="WARN",
                    message=(
                        f"⚠️ NEAR 24h low ${price_data.low_24h:.4f} "
                        f"fell below target ${thresholds['low_24h']:.2f}"
                    ),
                    triggered_value=price_data.low_24h,
                    threshold=thresholds["low_24h"],
                )
            )

    return alerts


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_telegram(price_data: PriceData, alerts: list[Alert]) -> str:
    """Format output as Telegram markdown message."""
    lines = [
        "💰 *NEAR Price Update*",
        f"Source: `{price_data.source}`",
        f"Price:  `${price_data.price_usd:.4f}`",
        f"24h Δ: `{price_data.change_24h_pct:+.2f}%`",
    ]
    if price_data.high_24h is not None:
        lines.append(f"High:   `${price_data.high_24h:.4f}`")
    if price_data.low_24h is not None:
        lines.append(f"Low:    `${price_data.low_24h:.4f}`")

    if alerts:
        lines.append("")
        lines.append("⚠️ *Alerts Triggered:*")
        for alert in alerts:
            lines.append(f"• {alert.message}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_config(args: argparse.Namespace) -> dict:
    """Merge config file with CLI overrides."""
    config: dict = {"thresholds": {}}
    config_path = Path(args.config)
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            config.setdefault("thresholds", {})
        except json.JSONDecodeError as exc:
            logger.error("Invalid config JSON: %s", exc)
            sys.exit(1)

    th = config["thresholds"]
    if args.above is not None:
        th["above"] = args.above
    if args.below is not None:
        th["below"] = args.below
    if args.change_pct is not None:
        th["change_pct"] = args.change_pct

    return config


def main() -> None:
    """Entry point for the NEAR price alert skill."""
    parser = argparse.ArgumentParser(
        description="NEAR token price alerts for OpenClaw — multi-source, configurable thresholds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Current price (human-readable)
  python3 price-alert.py --price

  # Check with CLI thresholds
  python3 price-alert.py --check --above 10 --below 2 --change-pct 5

  # JSON output from specific source
  python3 price-alert.py --price --source binance --json

  # Aggregate from all sources
  python3 price-alert.py --aggregate --json

  # Use config file
  python3 price-alert.py --check --config config.json
""",
    )
    parser.add_argument(
        "--config", "-c", default="config.json", help="Path to config JSON file"
    )
    parser.add_argument(
        "--source", "-s",
        choices=list(_FETCHERS.keys()),
        default=None,
        help="Preferred price source (default: auto-fallback)",
    )
    parser.add_argument("--check", action="store_true", help="Evaluate alert thresholds")
    parser.add_argument("--price", action="store_true", help="Print current NEAR price")
    parser.add_argument("--aggregate", action="store_true", help="Fetch from all sources and aggregate")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--above", type=float, default=None, help="Alert if price ≥ value")
    parser.add_argument("--below", type=float, default=None, help="Alert if price ≤ value")
    parser.add_argument("--change-pct", type=float, default=None, help="Alert if |24h change| ≥ value")
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Aggregate mode
    if args.aggregate:
        try:
            agg = aggregate_price()
        except RuntimeError as exc:
            msg = {"error": str(exc)}
            print(json.dumps(msg) if args.json else f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        if args.json:
            print(json.dumps(agg, indent=2))
        else:
            print(f"NEAR Price Aggregation ({len(agg['sources'])} sources)")
            print(f"  Average: ${agg['average_price_usd']:.4f}")
            print(f"  Range:   ${agg['min_price_usd']:.4f} – ${agg['max_price_usd']:.4f}")
            print(f"  Spread:  {agg['spread_pct']:.3f}%")
            print(f"  24h Δ:   {agg['average_change_24h_pct']:+.2f}%")
            if agg["errors"]:
                print(f"  Errors:  {agg['errors']}")
        return

    config = build_config(args)

    try:
        price_data = get_near_price(source=args.source)
    except RuntimeError as exc:
        msg = {"error": str(exc)}
        print(json.dumps(msg) if args.json else f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.price and not args.check:
        if args.json:
            print(json.dumps(asdict(price_data), indent=2))
        else:
            print(f"NEAR: ${price_data.price_usd:.4f} ({price_data.change_24h_pct:+.2f}%)")
        return

    alerts = check_alerts(price_data, config)

    if args.json:
        print(json.dumps({
            "price": asdict(price_data),
            "alerts": [asdict(a) for a in alerts],
            "triggered": len(alerts) > 0,
        }, indent=2))
    else:
        print(format_telegram(price_data, alerts))
        if not alerts:
            print("\n✅ No alert thresholds triggered.")
        else:
            sys.exit(2)  # non-zero so cron/wrapper knows alerts fired


if __name__ == "__main__":
    main()
