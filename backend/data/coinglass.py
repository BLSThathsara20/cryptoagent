"""Coinglass API fetcher for liquidations, long/short ratios, and open interest."""

import logging
from tenacity import retry, stop_after_attempt, wait_exponential

import httpx
from sqlalchemy.orm import Session

from config import settings
from db.models import Liquidation, LongShortRatio

logger = logging.getLogger(__name__)

COINGLASS_BASE = "https://open-api.coinglass.com/public/v2"


def _headers() -> dict:
    headers = {"accept": "application/json"}
    if settings.coinglass_api_key:
        headers["coinglassSecret"] = settings.coinglass_api_key
    return headers


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_liquidations(symbol: str = "BTC") -> list:
    """Fetch recent liquidation data for a symbol."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{COINGLASS_BASE}/liquidation_history",
            params={"symbol": symbol, "time_type": "h1"},
            headers=_headers(),
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", []) if isinstance(data, dict) else []
        logger.warning("Coinglass liquidations returned %s", resp.status_code)
        return []


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_long_short_ratio(symbol: str = "BTC") -> dict:
    """Fetch long/short ratio and open interest."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{COINGLASS_BASE}/long_short",
            params={"symbol": symbol, "time_type": "h1"},
            headers=_headers(),
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", [])
            return items[0] if items else {}
        logger.warning("Coinglass long/short returned %s", resp.status_code)
        return {}


async def store_coinglass_data(db: Session, symbols: list[str] | None = None) -> int:
    """Fetch and store liquidation and long/short data for watch coins."""
    symbols = symbols or settings.watch_coin_list[:5]
    count = 0
    for symbol in symbols:
        try:
            # Long/short ratio
            ls_data = await fetch_long_short_ratio(symbol)
            if ls_data:
                db.add(
                    LongShortRatio(
                        symbol=symbol,
                        long_ratio=ls_data.get("longRate") or ls_data.get("long_ratio"),
                        short_ratio=ls_data.get("shortRate") or ls_data.get("short_ratio"),
                        open_interest=ls_data.get("openInterest") or ls_data.get("open_interest"),
                    )
                )
                count += 1

            # Liquidations - store aggregate if available
            liq_data = await fetch_liquidations(symbol)
            if liq_data:
                for item in liq_data[:10]:
                    long_liq = item.get("longLiquidationUsd") or item.get("longVolUsd", 0)
                    short_liq = item.get("shortLiquidationUsd") or item.get("shortVolUsd", 0)
                    if long_liq:
                        db.add(
                            Liquidation(
                                symbol=symbol,
                                side="long",
                                size=float(long_liq),
                                price=item.get("price"),
                            )
                        )
                        count += 1
                    if short_liq:
                        db.add(
                            Liquidation(
                                symbol=symbol,
                                side="short",
                                size=float(short_liq),
                                price=item.get("price"),
                            )
                        )
                        count += 1
        except Exception as e:
            logger.error("Coinglass fetch failed for %s: %s", symbol, e)

    try:
        db.commit()
        logger.info("Stored %d Coinglass records", count)
    except Exception as e:
        logger.error("Coinglass commit failed: %s", e)
        db.rollback()
    return count
