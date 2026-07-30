"""Scheduler for all data fetching jobs (runs every 60 seconds)."""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from db.session import SessionLocal
from data.coingecko import store_coin_prices, store_market_dominance
from data.feargreed import store_fear_greed
from data.coinglass import store_coinglass_data
from data.news import store_market_news

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_last_ingestion_at: datetime | None = None  # last attempt
_last_ingestion_success_at: datetime | None = None
_ingestion_count = 0
_last_success_count = 0


def get_ingestion_status() -> dict:
    # Pulse uses last_run_at for freshness — only report successful runs
    return {
        "running": scheduler.running if scheduler else False,
        "last_run_at": (
            _last_ingestion_success_at.isoformat() if _last_ingestion_success_at else None
        ),
        "last_attempt_at": _last_ingestion_at.isoformat() if _last_ingestion_at else None,
        "total_cycles": _ingestion_count,
        "last_success_count": _last_success_count,
        "interval_seconds": 60,
    }


async def run_all_fetchers():
    """Execute all data fetchers in sequence. Marks live only when something succeeded."""
    global _last_ingestion_at, _last_ingestion_success_at, _ingestion_count, _last_success_count
    db = SessionLocal()
    _last_ingestion_at = datetime.utcnow()
    success = 0
    try:
        n = await store_coin_prices(db, limit=50)
        if n:
            success += 1
        if await store_market_dominance(db):
            success += 1
        if await store_fear_greed(db):
            success += 1
        cg = await store_coinglass_data(db, settings.watch_coin_list)
        if cg:
            success += 1
        news_n = await store_market_news(db, limit=30)
        if news_n:
            success += 1

        _ingestion_count += 1
        _last_success_count = success
        if success > 0:
            _last_ingestion_success_at = datetime.utcnow()
            logger.info("Data ingestion cycle complete (%d sources ok)", success)
        else:
            logger.warning(
                "Data ingestion cycle finished with 0 successes — likely offline; will retry"
            )
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
        coalesce=True,
        max_instances=1,
        misfire_grace_time=45,
    )
    scheduler.start()
    logger.info("Data ingestion scheduler started (60s interval)")


def stop_ingestion_scheduler():
    """Shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
