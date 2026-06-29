"""Scheduler for all data fetching jobs (runs every 60 seconds)."""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from datetime import datetime

from config import settings
from db.session import SessionLocal
from data.coingecko import store_coin_prices, store_market_dominance
from data.feargreed import store_fear_greed
from data.coinglass import store_coinglass_data

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_last_ingestion_at: datetime | None = None
_ingestion_count = 0


def get_ingestion_status() -> dict:
    return {
        "running": scheduler.running if scheduler else False,
        "last_run_at": _last_ingestion_at.isoformat() if _last_ingestion_at else None,
        "total_cycles": _ingestion_count,
        "interval_seconds": 60,
    }


async def run_all_fetchers():
    """Execute all data fetchers in sequence."""
    global _last_ingestion_at, _ingestion_count
    db = SessionLocal()
    try:
        await store_coin_prices(db, limit=50)
        await store_market_dominance(db)
        await store_fear_greed(db)
        await store_coinglass_data(db, settings.watch_coin_list)
        _last_ingestion_at = datetime.utcnow()
        _ingestion_count += 1
        logger.info("Data ingestion cycle complete")
    except Exception as e:
        logger.error("Data ingestion cycle failed: %s", e)
    finally:
        db.close()


def start_ingestion_scheduler():
    """Start the APScheduler job that runs every 60 seconds."""
    scheduler.add_job(
        run_all_fetchers,
        "interval",
        seconds=60,
        id="data_ingestion",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Data ingestion scheduler started (60s interval)")


def stop_ingestion_scheduler():
    """Shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
