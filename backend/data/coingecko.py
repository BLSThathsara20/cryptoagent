"""CoinGecko API fetcher for top coins and market dominance."""

import logging
from tenacity import retry, stop_after_attempt, wait_exponential

import httpx
from sqlalchemy.orm import Session

from db.models import CoinPrice, MarketDominance

logger = logging.getLogger(__name__)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_top_coins(limit: int = 50) -> list[dict]:
    """Fetch top coins by market cap from CoinGecko."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{COINGECKO_BASE}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": limit,
                "page": 1,
                "sparkline": "false",
            },
        )
        resp.raise_for_status()
        return resp.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_global_data() -> dict:
    """Fetch global market data including BTC/ETH dominance."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{COINGECKO_BASE}/global")
        resp.raise_for_status()
        return resp.json()


async def store_coin_prices(db: Session, limit: int = 50) -> int:
    """Fetch and store top coin prices."""
    try:
        coins = await fetch_top_coins(limit)
        count = 0
        for coin in coins:
            db.add(
                CoinPrice(
                    symbol=coin.get("symbol", "").upper(),
                    name=coin.get("name"),
                    price=coin.get("current_price", 0),
                    volume_24h=coin.get("total_volume"),
                    change_24h=coin.get("price_change_percentage_24h"),
                    market_cap=coin.get("market_cap"),
                    rank=coin.get("market_cap_rank"),
                )
            )
            count += 1
        db.commit()
        logger.info("Stored %d coin prices from CoinGecko", count)
        return count
    except Exception as e:
        logger.error("CoinGecko fetch failed: %s", e)
        db.rollback()
        return 0


async def store_market_dominance(db: Session) -> bool:
    """Fetch and store BTC/ETH dominance."""
    try:
        data = await fetch_global_data()
        global_data = data.get("data", {})
        db.add(
            MarketDominance(
                btc_dominance=global_data.get("market_cap_percentage", {}).get("btc"),
                eth_dominance=global_data.get("market_cap_percentage", {}).get("eth"),
                total_market_cap=global_data.get("total_market_cap", {}).get("usd"),
            )
        )
        db.commit()
        logger.info("Stored market dominance data")
        return True
    except Exception as e:
        logger.error("Dominance fetch failed: %s", e)
        db.rollback()
        return False
