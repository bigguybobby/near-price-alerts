"""Tests for NEAR price alert skill."""
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make scripts importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import price_alert as pa  # noqa: E402  (imported after path manipulation)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_price_data():
    return pa.PriceData(
        source="coingecko",
        price_usd=5.50,
        change_24h_pct=8.5,
        high_24h=6.00,
        low_24h=4.80,
        volume_24h_usd=200_000_000.0,
        timestamp=time.time(),
    )


@pytest.fixture
def empty_config():
    return {"thresholds": {}}


# ---------------------------------------------------------------------------
# PriceData dataclass
# ---------------------------------------------------------------------------

class TestPriceData:
    def test_defaults(self):
        pd = pa.PriceData(source="test", price_usd=5.0, change_24h_pct=1.0)
        assert pd.source == "test"
        assert pd.price_usd == 5.0
        assert pd.timestamp > 0

    def test_serialisable(self, sample_price_data):
        d = asdict(sample_price_data)
        assert isinstance(d, dict)
        assert "price_usd" in d


# ---------------------------------------------------------------------------
# check_alerts
# ---------------------------------------------------------------------------

class TestCheckAlerts:
    def test_above_threshold_triggered(self, sample_price_data):
        config = {"thresholds": {"above": 5.00}}
        alerts = pa.check_alerts(sample_price_data, config)
        assert len(alerts) == 1
        assert alerts[0].level == "CRITICAL"
        assert "above" in alerts[0].message.lower() or "$5" in alerts[0].message

    def test_above_threshold_not_triggered(self, sample_price_data):
        config = {"thresholds": {"above": 10.00}}
        alerts = pa.check_alerts(sample_price_data, config)
        assert len(alerts) == 0

    def test_below_threshold_triggered(self, sample_price_data):
        config = {"thresholds": {"below": 6.00}}
        alerts = pa.check_alerts(sample_price_data, config)
        assert any("below" in a.message.lower() or "dropped" in a.message.lower() for a in alerts)

    def test_below_threshold_not_triggered(self, sample_price_data):
        config = {"thresholds": {"below": 2.00}}
        alerts = pa.check_alerts(sample_price_data, config)
        assert len(alerts) == 0

    def test_change_pct_triggered(self, sample_price_data):
        # sample has 8.5% change
        config = {"thresholds": {"change_pct": 5.0}}
        alerts = pa.check_alerts(sample_price_data, config)
        assert any("24h" in a.message for a in alerts)

    def test_change_pct_not_triggered(self, sample_price_data):
        config = {"thresholds": {"change_pct": 20.0}}
        alerts = pa.check_alerts(sample_price_data, config)
        assert not any("24h" in a.message for a in alerts)

    def test_high_24h_triggered(self, sample_price_data):
        config = {"thresholds": {"high_24h": 5.90}}
        alerts = pa.check_alerts(sample_price_data, config)
        assert len(alerts) == 1
        assert "high" in alerts[0].message.lower()

    def test_low_24h_triggered(self, sample_price_data):
        config = {"thresholds": {"low_24h": 5.00}}
        alerts = pa.check_alerts(sample_price_data, config)
        assert len(alerts) == 1
        assert "low" in alerts[0].message.lower()

    def test_empty_config_no_alerts(self, sample_price_data, empty_config):
        alerts = pa.check_alerts(sample_price_data, empty_config)
        assert alerts == []

    def test_multiple_alerts_combined(self, sample_price_data):
        config = {"thresholds": {"above": 5.00, "change_pct": 5.0}}
        alerts = pa.check_alerts(sample_price_data, config)
        assert len(alerts) == 2

    def test_negative_change(self):
        pd = pa.PriceData(source="test", price_usd=3.0, change_24h_pct=-12.0)
        config = {"thresholds": {"change_pct": 10.0}}
        alerts = pa.check_alerts(pd, config)
        assert len(alerts) == 1
        assert "📉" in alerts[0].message


# ---------------------------------------------------------------------------
# format_telegram
# ---------------------------------------------------------------------------

class TestFormatTelegram:
    def test_basic_format(self, sample_price_data):
        msg = pa.format_telegram(sample_price_data, [])
        assert "NEAR" in msg
        assert "5.5" in msg

    def test_includes_alerts(self, sample_price_data):
        alert = pa.Alert(level="CRITICAL", message="Test alert", triggered_value=5.5, threshold=5.0)
        msg = pa.format_telegram(sample_price_data, [alert])
        assert "Test alert" in msg

    def test_high_low_shown(self, sample_price_data):
        msg = pa.format_telegram(sample_price_data, [])
        assert "High" in msg or "6.0" in msg


# ---------------------------------------------------------------------------
# Fetcher mocking
# ---------------------------------------------------------------------------

class TestFetchers:
    def _mock_http_get_coingecko(self, url):
        return {"near": {"usd": 5.5, "usd_24h_change": 3.2}}

    @patch("price_alert._http_get")
    def test_fetch_coingecko(self, mock_get):
        mock_get.return_value = {"near": {"usd": 5.5, "usd_24h_change": 3.2}}
        pd = pa.fetch_coingecko()
        assert pd.price_usd == 5.5
        assert pd.change_24h_pct == 3.2
        assert pd.source == "coingecko"

    @patch("price_alert._http_get")
    def test_fetch_binance(self, mock_get):
        mock_get.return_value = {
            "lastPrice": "5.42",
            "priceChangePercent": "-1.5",
            "quoteVolume": "10000000",
            "highPrice": "5.80",
            "lowPrice": "5.10",
        }
        pd = pa.fetch_binance()
        assert pd.price_usd == pytest.approx(5.42)
        assert pd.source == "binance"

    @patch("price_alert._http_get")
    def test_fetch_kraken(self, mock_get):
        mock_get.return_value = {
            "result": {
                "NEARUSD": {
                    "c": ["5.60", "1"],
                    "o": "5.00",
                    "h": ["5.80", "5.80"],
                    "l": ["4.90", "4.90"],
                }
            }
        }
        pd = pa.fetch_kraken()
        assert pd.price_usd == pytest.approx(5.60)
        assert pd.source == "kraken"
        assert pd.change_24h_pct == pytest.approx(12.0)

    @patch("price_alert._http_get")
    def test_fetch_coincap(self, mock_get):
        mock_get.return_value = {
            "data": {
                "priceUsd": "5.45",
                "changePercent24Hr": "2.1",
                "volumeUsd24Hr": "50000000",
            }
        }
        pd = pa.fetch_coincap()
        assert pd.price_usd == pytest.approx(5.45)
        assert pd.source == "coincap"


# ---------------------------------------------------------------------------
# get_near_price with fallback
# ---------------------------------------------------------------------------

class TestGetNearPrice:
    @patch("price_alert.fetch_coingecko")
    def test_returns_first_success(self, mock_cg):
        mock_cg.return_value = pa.PriceData(source="coingecko", price_usd=5.5, change_24h_pct=1.0)
        pd = pa.get_near_price()
        assert pd.source == "coingecko"

    @patch("price_alert.fetch_coingecko", side_effect=Exception("timeout"))
    @patch("price_alert.fetch_binance")
    def test_fallback_to_binance(self, mock_bn, mock_cg):
        mock_bn.return_value = pa.PriceData(source="binance", price_usd=5.4, change_24h_pct=0.5)
        pd = pa.get_near_price(retries=1)
        assert pd.source == "binance"

    @patch("price_alert.fetch_coingecko", side_effect=Exception("fail"))
    @patch("price_alert.fetch_binance", side_effect=Exception("fail"))
    @patch("price_alert.fetch_kraken", side_effect=Exception("fail"))
    @patch("price_alert.fetch_coincap", side_effect=Exception("fail"))
    def test_raises_when_all_fail(self, *mocks):
        with pytest.raises(RuntimeError, match="All price sources failed"):
            pa.get_near_price(retries=1)


# ---------------------------------------------------------------------------
# aggregate_price
# ---------------------------------------------------------------------------

class TestAggregatePrice:
    @patch("price_alert.fetch_coingecko")
    @patch("price_alert.fetch_binance")
    @patch("price_alert.fetch_kraken", side_effect=Exception("fail"))
    @patch("price_alert.fetch_coincap", side_effect=Exception("fail"))
    def test_partial_success(self, _1, _2, mock_bn, mock_cg):
        mock_cg.return_value = pa.PriceData(source="coingecko", price_usd=5.5, change_24h_pct=1.0)
        mock_bn.return_value = pa.PriceData(source="binance", price_usd=5.6, change_24h_pct=1.5)
        result = pa.aggregate_price()
        assert len(result["sources"]) == 2
        assert result["average_price_usd"] == pytest.approx(5.55)
        assert "kraken" in result["errors"]

    @patch("price_alert.fetch_coingecko", side_effect=Exception("fail"))
    @patch("price_alert.fetch_binance", side_effect=Exception("fail"))
    @patch("price_alert.fetch_kraken", side_effect=Exception("fail"))
    @patch("price_alert.fetch_coincap", side_effect=Exception("fail"))
    def test_all_fail_raises(self, *_):
        with pytest.raises(RuntimeError):
            pa.aggregate_price()
