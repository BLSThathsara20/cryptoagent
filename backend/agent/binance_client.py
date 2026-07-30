"""Shared Binance / CCXT client for reading account balances."""

import logging
import time

import ccxt

from config import settings

logger = logging.getLogger(__name__)

STABLECOINS = {"USDT", "USDC", "BUSD", "FDUSD", "TUSD", "DAI"}

_last_diagnose: dict | None = None
_last_diagnose_at: float = 0


def invalidate_binance_diagnose():
    """Clear cached diagnose so the next check hits the network (after offline)."""
    global _last_diagnose, _last_diagnose_at
    _last_diagnose = None
    _last_diagnose_at = 0


def _key() -> str:
    return (settings.binance_api_key or "").strip()


def _secret() -> str:
    return (settings.binance_secret or "").strip()


def is_configured() -> bool:
    return bool(_key() and _secret())


def get_public_exchange() -> ccxt.binance:
    """Unauthenticated client for public market data."""
    return ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "spot"}})


def get_exchange() -> ccxt.binance | None:
    """Return authenticated Binance exchange instance."""
    if not is_configured():
        return None
    try:
        return ccxt.binance(
            {
                "apiKey": _key(),
                "secret": _secret(),
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
        )
    except Exception as e:
        logger.error("Failed to create Binance client: %s", e)
        return None


def _parse_binance_error(exc: Exception) -> dict:
    msg = str(exc)
    code = None
    if "-2015" in msg or "Invalid API-key" in msg:
        code = -2015
        hint = (
            "Invalid API key, IP not whitelisted, or missing Reading permission. "
            "In Binance → API Management: enable Read, add this machine’s public IP "
            "(or disable IP restriction), then recreate keys if needed."
        )
    elif "-2014" in msg:
        code = -2014
        hint = "API key format invalid — check for extra spaces or truncated key in .env."
    elif "-1022" in msg:
        code = -1022
        hint = "Signature error — BINANCE_SECRET may be wrong."
    else:
        hint = "Check API key, secret, Reading permission, and IP whitelist."
    return {"code": code, "message": msg[:240], "hint": hint}


def diagnose_binance(force: bool = False, cache_only: bool = False) -> dict:
    """
    Lightweight Binance health check.
    Separates public market reachability from private account access.
    cache_only=True never hits the network (for high-frequency UI pulse).
    """
    global _last_diagnose, _last_diagnose_at
    now = time.time()
    if cache_only:
        if _last_diagnose:
            return _last_diagnose
        return {
            "configured": is_configured(),
            "market_ok": False,  # unknown until first real check — not LIVE
            "account_ok": False,
            "assets": 0,
            "code": None,
            "message": "Pending first Binance check",
            "hint": "",
            "pending": True,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    if not force and _last_diagnose and now - _last_diagnose_at < 90:
        return _last_diagnose

    result = {
        "configured": is_configured(),
        "market_ok": False,
        "account_ok": False,
        "assets": 0,
        "code": None,
        "message": "",
        "hint": "",
        "pending": False,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    try:
        pub = get_public_exchange()
        pub.fetch_ticker("BTC/USDT")
        result["market_ok"] = True
    except Exception as e:
        result["message"] = f"Public market unreachable: {e}"
        result["hint"] = "Network/hotspot may be offline — market data will resume when online."
        _last_diagnose = result
        _last_diagnose_at = now
        return result

    if not is_configured():
        result["message"] = "Market OK — account keys not set (paper mode OK)"
        _last_diagnose = result
        _last_diagnose_at = now
        return result

    exchange = get_exchange()
    if not exchange:
        result["message"] = "Could not build authenticated client"
        result["hint"] = "Check BINANCE_API_KEY / BINANCE_SECRET in .env"
        _last_diagnose = result
        _last_diagnose_at = now
        return result

    try:
        balance = exchange.fetch_balance()
        assets = 0
        for asset, amounts in balance.items():
            if asset in ("info", "free", "used", "total", "datetime", "timestamp"):
                continue
            if isinstance(amounts, dict) and float(amounts.get("total") or 0) > 0:
                assets += 1
        result["account_ok"] = True
        result["assets"] = assets
        result["message"] = f"Account OK — {assets} assets with balance"
    except Exception as e:
        parsed = _parse_binance_error(e)
        result["code"] = parsed["code"]
        result["message"] = parsed["message"]
        result["hint"] = parsed["hint"]
        logger.error("Binance account check failed: %s", e)

    _last_diagnose = result
    _last_diagnose_at = now
    return result


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
    """Fetch USD prices via public Binance API (no private key required)."""
    prices = {s: 1.0 for s in symbols if s in STABLECOINS}
    crypto = [s for s in symbols if s not in STABLECOINS]
    if not crypto:
        return prices

    try:
        exchange = get_public_exchange()
        for asset in crypto:
            pair = f"{asset}/USDT"
            try:
                ticker = exchange.fetch_ticker(pair)
                prices[asset] = float(ticker.get("last") or ticker.get("close") or 0)
            except Exception:
                try:
                    ticker = exchange.fetch_ticker(f"{asset}/BTC")
                    btc = exchange.fetch_ticker("BTC/USDT")
                    prices[asset] = float(ticker["last"]) * float(btc["last"])
                except Exception:
                    prices[asset] = 0.0
    except Exception as e:
        logger.warning("Price fetch partial failure: %s", e)

    return prices
