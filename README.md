# NEAR Price Alerts — OpenClaw Skill

Real-time NEAR token price alerts with **multi-source price fetching**, configurable thresholds, and JSON output for automation pipelines.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-pytest-green.svg)](tests/)

---

## Features

- 🌐 **4 price sources**: CoinGecko, Binance, Kraken, CoinCap — with automatic fallback
- 🚨 **Rich alert types**: above/below thresholds, 24h % change, 24h high/low
- 📊 **Aggregation mode**: fetch from all sources simultaneously, compute spread
- 🔄 **Retry logic**: configurable retries per source with exponential back-off
- 📱 **Telegram-formatted output** or structured JSON for downstream tools
- ⚙️ **Config file** or pure CLI — no dependencies beyond stdlib

---

## Installation

```bash
# Clone or pull the repo
cd ~/projects/near-market/near-price-alerts

# No pip install needed — stdlib only
python3 --version   # 3.8+ required

# Copy example config
cp config.example.json config.json
```

---

## Usage

### Print current price

```bash
python3 scripts/price-alert.py --price
# NEAR: $5.4231 (+3.42%)

python3 scripts/price-alert.py --price --source binance
python3 scripts/price-alert.py --price --json
```

### Check alert thresholds (CLI)

```bash
# Alert if price above $10 OR below $2 OR 24h change > ±5%
python3 scripts/price-alert.py --check --above 10 --below 2 --change-pct 5

# Returns exit code 2 if any alert fires (useful in cron/scripts)
```

### Check with config file

```bash
cp config.example.json config.json
# Edit config.json with your thresholds
python3 scripts/price-alert.py --check --config config.json --json
```

### Aggregate from all sources

```bash
python3 scripts/price-alert.py --aggregate
python3 scripts/price-alert.py --aggregate --json
```

### Verbose / debug mode

```bash
python3 scripts/price-alert.py --price --verbose
```

---

## Configuration

`config.json` (copy from `config.example.json`):

```json
{
  "source": "coingecko",
  "thresholds": {
    "above": 10.00,
    "below": 2.00,
    "change_pct": 5.0,
    "high_24h": 9.00,
    "low_24h": 3.00
  }
}
```

| Key | Type | Description |
|-----|------|-------------|
| `source` | string | Preferred price source (`coingecko`, `binance`, `kraken`, `coincap`) |
| `thresholds.above` | float | Fire CRITICAL alert if price ≥ this value |
| `thresholds.below` | float | Fire CRITICAL alert if price ≤ this value |
| `thresholds.change_pct` | float | Fire alert if \|24h change\| ≥ this percent |
| `thresholds.high_24h` | float | Fire WARN if 24h high ≥ this value |
| `thresholds.low_24h` | float | Fire WARN if 24h low ≤ this value |

---

## API Reference

### `get_near_price(source, fallback, retries) → PriceData`

Fetch NEAR price with fallback across sources.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `source` | `str \| None` | `None` | Preferred source; `None` = auto |
| `fallback` | `bool` | `True` | Try other sources on failure |
| `retries` | `int` | `3` | Attempts per source |

### `aggregate_price(sources) → dict`

Fetch from multiple sources simultaneously.

Returns: `{ sources, average_price_usd, min_price_usd, max_price_usd, spread_pct, errors }`

### `check_alerts(price_data, config) → list[Alert]`

Evaluate a `PriceData` object against config thresholds.

Returns list of `Alert(level, message, triggered_value, threshold)`.

### `format_telegram(price_data, alerts) → str`

Format output as Telegram markdown.

---

## Price Sources

| Source | URL | Notes |
|--------|-----|-------|
| CoinGecko | `api.coingecko.com` | Free tier, rate-limited; includes 24h change |
| Binance | `api.binance.com` | High precision, includes volume/high/low |
| Kraken | `api.kraken.com` | EU exchange; NEAR/USD pair |
| CoinCap | `api.coincap.io` | Real-time; includes supply data |

---

## Testing

```bash
pip install pytest
cd ~/projects/near-market/near-price-alerts
pytest tests/ -v
```

---

## OpenClaw Cron Integration

Add to your OpenClaw schedule:

```json
{
  "cron": "*/15 * * * *",
  "command": "python3 ~/projects/near-market/near-price-alerts/scripts/price-alert.py --check --config ~/projects/near-market/near-price-alerts/config.json"
}
```

---

## License

[MIT](LICENSE) © 2025 bigguybobby
