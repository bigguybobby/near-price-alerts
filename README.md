# NEAR Price Alerts — OpenClaw Skill

Real-time NEAR token price alerts using CoinGecko free API.

## Quick Start

```bash
# Check current price
python3 scripts/price-alert.py --price

# Check with alert thresholds
python3 scripts/price-alert.py --check --above 10 --below 2 --change-pct 5

# Use config file
cp config.example.json config.json
python3 scripts/price-alert.py --check --config config.json

# JSON output
python3 scripts/price-alert.py --check --json
```

## Requirements
- Python 3.8+ (stdlib only, no dependencies)

## OpenClaw Integration
Add to your cron schedule for automated monitoring. Output is Telegram-formatted markdown.

## License
MIT
