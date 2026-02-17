#!/usr/bin/env python3
"""NEAR token price alert skill for OpenClaw. Uses CoinGecko free API."""

import argparse
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=near&vs_currencies=usd&include_24hr_change=true"

def get_near_price():
    """Fetch current NEAR price from CoinGecko free API."""
    req = urllib.request.Request(COINGECKO_URL, headers={"Accept": "application/json", "User-Agent": "OpenClaw-NEAR-Alerts/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    return data["near"]["usd"], data["near"].get("usd_24h_change", 0)

def check_alerts(price, change_24h, config):
    """Check price against configured thresholds. Returns list of alert messages."""
    alerts = []
    thresholds = config.get("thresholds", {})
    if "above" in thresholds and price >= thresholds["above"]:
        alerts.append(f"🚀 NEAR is above ${thresholds['above']:.2f}! Current: ${price:.4f}")
    if "below" in thresholds and price <= thresholds["below"]:
        alerts.append(f"🔻 NEAR dropped below ${thresholds['below']:.2f}! Current: ${price:.4f}")
    pct = thresholds.get("change_pct", None)
    if pct and abs(change_24h) >= pct:
        direction = "📈" if change_24h > 0 else "📉"
        alerts.append(f"{direction} NEAR 24h change: {change_24h:+.2f}% (threshold: ±{pct}%)")
    return alerts

def format_telegram(price, change_24h, alerts):
    """Format output for Telegram notification."""
    msg = f"💰 *NEAR Price Update*\nPrice: `${price:.4f}`\n24h Change: `{change_24h:+.2f}%`"
    if alerts:
        msg += "\n\n⚠️ *Alerts:*\n" + "\n".join(f"• {a}" for a in alerts)
    return msg

def main():
    parser = argparse.ArgumentParser(description="NEAR token price alerts for OpenClaw")
    parser.add_argument("--config", "-c", type=str, default="config.json", help="Path to config JSON file")
    parser.add_argument("--check", action="store_true", help="Check price and evaluate alerts")
    parser.add_argument("--price", action="store_true", help="Just print current NEAR price")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--above", type=float, help="Alert if price above this value")
    parser.add_argument("--below", type=float, help="Alert if price below this value")
    parser.add_argument("--change-pct", type=float, help="Alert if 24h change exceeds ±this percent")
    args = parser.parse_args()

    # Build config from file or CLI args
    config = {"thresholds": {}}
    config_path = Path(args.config)
    if config_path.exists():
        config = json.loads(config_path.read_text())
    if args.above: config.setdefault("thresholds", {})["above"] = args.above
    if args.below: config.setdefault("thresholds", {})["below"] = args.below
    if args.change_pct: config.setdefault("thresholds", {})["change_pct"] = args.change_pct

    try:
        price, change_24h = get_near_price()
    except Exception as e:
        print(json.dumps({"error": str(e)}) if args.json else f"Error fetching price: {e}", file=sys.stderr)
        sys.exit(1)

    if args.price and not args.check:
        if args.json:
            print(json.dumps({"price_usd": price, "change_24h_pct": change_24h}))
        else:
            print(f"NEAR: ${price:.4f} ({change_24h:+.2f}%)")
        return

    alerts = check_alerts(price, change_24h, config)
    if args.json:
        print(json.dumps({"price_usd": price, "change_24h_pct": change_24h, "alerts": alerts, "triggered": len(alerts) > 0}))
    else:
        print(format_telegram(price, change_24h, alerts))

if __name__ == "__main__":
    main()
