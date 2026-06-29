"""Data retention and database maintenance for long-running deployments."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import text, func
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from db.session import SessionLocal, engine
from db.models import (
    CoinPrice,
    MarketDominance,
    OrderBookEntry,
    LiveTrade,
    Liquidation,
    LongShortRatio,
    FearGreedIndex,
    PortfolioSnapshot,
    SystemAlert,
)

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_last_maintenance_at: datetime | None = None
_last_cleanup_stats: dict = {}


def get_maintenance_status() -> dict:
    return {
        "last_run_at": _last_maintenance_at.isoformat() if _last_maintenance_at else None,
        "last_cleanup": _last_cleanup_stats,
        "retention_policy": {
            "order_book_days": settings.retain_orderbook_days,
            "live_trades_days": settings.retain_live_trades_days,
            "coin_prices_days": settings.retain_coin_prices_days,
            "market_meta_days": settings.retain_market_meta_days,
            "alerts_days": settings.retain_alerts_days,
            "portfolio_snapshots_days": settings.retain_portfolio_snapshots_days,
        },
    }


def get_database_stats(db) -> dict:
    """Row counts and estimated footprint for monitoring."""
    tables = [
        ("coin_prices", CoinPrice),
        ("order_book", OrderBookEntry),
        ("live_trades", LiveTrade),
        ("agent_decisions", None),
        ("system_alerts", SystemAlert),
        ("portfolio_snapshots", PortfolioSnapshot),
    ]
    counts = {}
    for name, model in tables:
        if model:
            counts[name] = db.query(func.count(model.id)).scalar() or 0
        else:
            from db.models import AgentDecision
            counts[name] = db.query(func.count(AgentDecision.id)).scalar() or 0

    # PostgreSQL database size
    size_mb = 0
    try:
        result = db.execute(
            text("SELECT pg_database_size(current_database()) / 1024 / 1024 AS size_mb")
        ).scalar()
        size_mb = round(float(result or 0), 1)
    except Exception:
        pass

    return {"table_counts": counts, "database_size_mb": size_mb}


def _delete_older_than(db, model, days: int, date_col="timestamp") -> int:
    col = getattr(model, date_col)
    cutoff = datetime.utcnow() - timedelta(days=days)
    count = db.query(model).filter(col < cutoff).delete(synchronize_session=False)
    return count


def run_data_retention() -> dict:
    """Delete old high-volume data. Keeps agent decisions & memories forever."""
    global _last_maintenance_at, _last_cleanup_stats
    db = SessionLocal()
    stats = {}
    try:
        stats["order_book"] = _delete_older_than(db, OrderBookEntry, settings.retain_orderbook_days)
        stats["live_trades"] = _delete_older_than(db, LiveTrade, settings.retain_live_trades_days)
        stats["coin_prices"] = _delete_older_than(db, CoinPrice, settings.retain_coin_prices_days)
        stats["market_dominance"] = _delete_older_than(db, MarketDominance, settings.retain_market_meta_days)
        stats["fear_greed"] = _delete_older_than(db, FearGreedIndex, settings.retain_market_meta_days)
        stats["long_short"] = _delete_older_than(db, LongShortRatio, settings.retain_market_meta_days)
        stats["liquidations"] = _delete_older_than(db, Liquidation, settings.retain_market_meta_days)
        stats["portfolio_snapshots"] = _delete_older_than(
            db, PortfolioSnapshot, settings.retain_portfolio_snapshots_days, "created_at"
        )
        # Read alerts older than N days
        alert_cutoff = datetime.utcnow() - timedelta(days=settings.retain_alerts_days)
        stats["alerts"] = (
            db.query(SystemAlert)
            .filter(SystemAlert.created_at < alert_cutoff, SystemAlert.read.is_(True))
            .delete(synchronize_session=False)
        )
        db.commit()

        # Reclaim disk space (run weekly, lightweight enough daily too)
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("VACUUM ANALYZE"))

        _last_maintenance_at = datetime.utcnow()
        _last_cleanup_stats = stats
        total = sum(stats.values())
        logger.info("Data retention complete — deleted %d rows: %s", total, stats)

        if total > 10000:
            from alerts.manager import create_alert
            create_alert(
                db, "info", "system", "Database Cleanup",
                f"Removed {total:,} old rows. DB size optimized for long-run stability.",
            )
        return stats
    except Exception as e:
        logger.error("Data retention failed: %s", e)
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()


def start_maintenance_scheduler():
    """Run retention daily at 03:00 UTC and every 6 hours as backup."""
    scheduler.add_job(
        run_data_retention,
        "cron",
        hour=3,
        minute=0,
        id="daily_retention",
        replace_existing=True,
    )
    scheduler.add_job(
        run_data_retention,
        "interval",
        hours=6,
        id="interval_retention",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
    logger.info("Maintenance scheduler started (retention daily + every 6h)")


def stop_maintenance_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
