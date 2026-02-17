# near-price-alerts

## Description
NEAR token price monitoring and alert skill for OpenClaw. Fetches real-time NEAR/USD price from CoinGecko free API and triggers alerts based on configurable thresholds.

## Triggers
- Cron schedule (e.g., every 5 minutes)
- Manual invocation

## Commands
- `price-alert --price` — Show current NEAR price
- `price-alert --check` — Check price against configured thresholds
- `price-alert --check --json` — JSON output for programmatic use

## Configuration
Copy `config.example.json` to `config.json` and set your thresholds:
- `above` — Alert when price exceeds this USD value
- `below` — Alert when price drops below this USD value
- `change_pct` — Alert on 24h percentage change exceeding ±threshold

## Output
Telegram-formatted markdown messages with price, 24h change, and triggered alerts.
