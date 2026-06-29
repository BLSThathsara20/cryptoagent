"""Alternative.me Fear & Greed Index fetcher."""

import logging
from tenacity import retry, stop_after_attempt, wait_exponential

import httpx
from sqlalchemy.orm import Session

from db.models import FearGreedIndex

logger = logging.getLogger(__name__)

FEAR_GREED_URL = "https://api.alternative.me/fng/"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_fear_greed() -> dict:
    """Fetch current Fear & Greed Index."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(FEAR_GREED_URL, params={"limit": 1})
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [{}])[0]


async def store_fear_greed(db: Session) -> bool:
    """Fetch and store Fear & Greed Index."""
    try:
        data = await fetch_fear_greed()
        db.add(
            FearGreedIndex(
                value=int(data.get("value", 50)),
                classification=data.get("value_classification", "Neutral"),
            )
        )
        db.commit()
        logger.info("Stored Fear & Greed Index: %s", data.get("value"))
        return True
    except Exception as e:
        logger.error("Fear & Greed fetch failed: %s", e)
        db.rollback()
        return False
