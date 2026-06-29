"""Shared Binance / CCXT client for reading account balances."""

import logging

import ccxt

from config import settings

logger = logging.getLogger(__name__)

STABLECOINS = {"USDT", "USDC", "BUSD", "FDUSD", "TUSD", "DAI"}


def is_configured() -> bool:
    return bool(settings.binance_api_key and settings.binance_secret)


def get_exchange() -> ccxt.binance | None:
    """Return authenticated Binance exchange instance."""
    if not is_configured():
        return None
    try:
        return ccxt.binance(
            {
                "apiKey": settings.binance_api_key,
                "secret": settings.binance_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
        )
    except Exception as e:
        logger.error("Failed to create Binance client: %s", e)
        return None


def fetch_spot_balances() -> dict | None:
    """
    Fetch non-zero spot balances from Binance.
    Returns {asset: {free, used, total}} or None if unavailable.
    """
    exchange = get_exchange()
    if not exchange:
        return None
    try:
        balance = exchange.fetch_balance()
        result = {}
        for asset, amounts in balance.items():
            if asset in ("info", "free", "used", "total", "datetime", "timestamp"):
                continue
            if not isinstance(amounts, dict):
                continue
            total = float(amounts.get("total") or 0)
            if total <= 0:
                continue
            result[asset.upper()] = {
                "free": float(amounts.get("free") or 0),
                "used": float(amounts.get("used") or 0),
                "total": total,
            }
        return result
    except Exception as e:
        logger.error("Failed to fetch Binance balances: %s", e)
        return None


def get_usd_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch USD prices for assets via CCXT ticker or return stables as 1.0."""
    exchange = get_exchange()
    prices = {s: 1.0 for s in symbols if s in STABLECOINS}
    crypto = [s for s in symbols if s not in STABLECOINS]

    if not exchange or not crypto:
        return prices

    try:
        for asset in crypto:
            pair = f"{asset}/USDT"
            try:
                ticker = exchange.fetch_ticker(pair)
                prices[asset] = float(ticker.get("last") or ticker.get("close") or 0)
            except Exception:
                # Try BTC route
                try:
                    ticker = exchange.fetch_ticker(f"{asset}/BTC")
                    btc = exchange.fetch_ticker("BTC/USDT")
                    prices[asset] = float(ticker["last"]) * float(btc["last"])
                except Exception:
                    prices[asset] = 0.0
    except Exception as e:
        logger.warning("Price fetch partial failure: %s", e)

    return prices
