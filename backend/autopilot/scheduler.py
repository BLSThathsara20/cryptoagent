"""Autopilot — health checks, stuck-agent recovery, zero-touch operations."""

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from db.session import SessionLocal
from db.models import AgentStatus
from data.retention import get_database_stats
from data.binance_ws import get_ws_status
from data.ingestion import get_ingestion_status
from alerts.manager import create_alert

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_last_health_at: datetime | None = None
_autopilot_issues: list[str] = []


def get_autopilot_status(db) -> dict:
    """Everything that runs automatically — for Settings dashboard."""
    agent = db.query(AgentStatus).first()
    ws = get_ws_status()
    ingestion = get_ingestion_status()
    db_stats = get_database_stats(db)

    tasks = [
        {"name": "Market data ingestion", "interval": "60s", "active": ingestion.get("running"), "manual": False},
        {"name": "Binance WebSocket", "interval": "real-time", "active": ws.get("status") == "connected", "manual": False},
        {"name": "Fund Manager Agent", "interval": f"{settings.agent_loop_interval}s", "active": True, "manual": False},
        {"name": "Trading Agent (AI)", "interval": f"{settings.agent_loop_interval}s", "active": True, "manual": False},
        {"name": "Paper/Live trade execution", "interval": "on signal", "active": True, "manual": False},
        {"name": "Learn from wins/losses", "interval": "on trade close", "active": True, "manual": False},
        {"name": "Database cleanup", "interval": "daily + 6h", "active": True, "manual": False},
        {"name": "Auto DB backup", "interval": "daily 02:00", "active": settings.auto_backup_enabled, "manual": False},
        {"name": "Health self-check", "interval": "15 min", "active": True, "manual": False},
        {"name": "Stuck agent recovery", "interval": "15 min", "active": settings.auto_recovery_enabled, "manual": False},
        {"name": "System alerts", "interval": "on event", "active": True, "manual": False},
    ]

    return {
        "mode": "full_autopilot",
        "user_action_required": False,
        "trading_mode": "live" if settings.live_mode else "paper",
        "last_health_check": _last_health_at.isoformat() if _last_health_at else None,
        "issues": _autopilot_issues,
        "automated_tasks": tasks,
        "agent_last_run": agent.last_run_at.isoformat() if agent and agent.last_run_at else None,
        "database_size_mb": db_stats.get("database_size_mb"),
    }


async def run_health_check():
    """Self-diagnose and alert — no user intervention needed."""
    global _last_health_at, _autopilot_issues
    _last_health_at = datetime.utcnow()
    _autopilot_issues = []
    db = SessionLocal()

    try:
        db_stats = get_database_stats(db)
        size_mb = db_stats.get("database_size_mb", 0)

        if size_mb > settings.db_size_warn_mb:
            _autopilot_issues.append(f"Database large ({size_mb} MB)")
            create_alert(
                db, "warning", "system", "Database Size Warning",
                f"DB is {size_mb} MB. Cleanup runs automatically — no action needed unless > {settings.db_size_warn_mb * 2} MB.",
            )

        ws = get_ws_status()
        if ws.get("status") != "connected":
            _autopilot_issues.append("Binance WebSocket disconnected (auto-reconnecting)")

        agent = db.query(AgentStatus).first()
        if agent and agent.last_run_at:
            max_gap = timedelta(seconds=settings.agent_loop_interval * 3)
            if datetime.utcnow() - agent.last_run_at.replace(tzinfo=None) > max_gap:
                _autopilot_issues.append("Agent overdue — triggering recovery")
                if settings.auto_recovery_enabled:
                    from agent.loop import trigger_agent_cycle_now
                    create_alert(db, "warning", "system", "Agent Auto-Recovery", "Agent was stuck — restarted cycle automatically.")
                    await trigger_agent_cycle_now()

        if not _autopilot_issues:
            logger.debug("Autopilot health check: all OK")
    except Exception as e:
        logger.error("Health check failed: %s", e)
        _autopilot_issues.append(str(e))
    finally:
        db.close()


def start_autopilot_scheduler():
    scheduler.add_job(
        run_health_check,
        "interval",
        minutes=15,
        id="health_check",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
    logger.info("Autopilot health scheduler started (every 15 min)")


def stop_autopilot_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
