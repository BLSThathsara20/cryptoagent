"""Autopilot — health checks, stuck-agent recovery, post-offline service restart."""

import asyncio
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from db.session import SessionLocal
from db.models import AgentStatus
from data.retention import get_database_stats
from data.binance_ws import get_ws_status, ensure_ws_running
from data.ingestion import get_ingestion_status, run_all_fetchers
from alerts.manager import create_alert

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_last_health_at: datetime | None = None
_last_recover_at: datetime | None = None
_autopilot_issues: list[str] = []
_was_offline = False


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
        {"name": "Offline recovery", "interval": "2 min", "active": True, "manual": False},
        {"name": "Validation Agent", "interval": "15 min", "active": True, "manual": False},
        {"name": "Stuck agent recovery", "interval": "15 min", "active": settings.auto_recovery_enabled, "manual": False},
        {"name": "System alerts", "interval": "on event", "active": True, "manual": False},
    ]

    return {
        "mode": "full_autopilot",
        "user_action_required": False,
        "trading_mode": "live" if settings.live_mode else "paper",
        "last_health_check": _last_health_at.isoformat() if _last_health_at else None,
        "last_recover_at": _last_recover_at.isoformat() if _last_recover_at else None,
        "issues": _autopilot_issues,
        "automated_tasks": tasks,
        "agent_last_run": agent.last_run_at.isoformat() if agent and agent.last_run_at else None,
        "database_size_mb": db_stats.get("database_size_mb"),
    }


async def recover_after_offline():
    """
    Runs every 2 minutes: restart dead WebSocket, refresh Binance diagnose,
    kick ingestion if feeds look stale. Fixes "came back online but services stuck".
    """
    global _last_recover_at, _was_offline, _autopilot_issues
    _last_recover_at = datetime.utcnow()
    ws = get_ws_status()
    ingest = get_ingestion_status()

    ws_down = ws.get("status") != "connected" or not ws.get("task_alive", True)
    ingest_stale = True
    if ingest.get("last_run_at"):
        try:
            age = (datetime.utcnow() - datetime.fromisoformat(ingest["last_run_at"])).total_seconds()
            ingest_stale = age > 180
        except Exception:
            ingest_stale = True

    offline_now = ws_down or ingest_stale
    if offline_now:
        _was_offline = True
        logger.info(
            "Recovery check: ws_down=%s ingest_stale=%s — ensuring services",
            ws_down,
            ingest_stale,
        )

    actions = []
    try:
        if ensure_ws_running():
            actions.append("websocket_respawned")

        from agent.loop import (
            ensure_agent_loop_running,
            is_agent_loop_running,
            restart_agent_loop,
            trigger_agent_cycle_now,
        )
        from db.models import AgentStatus as _AgentStatus

        # Always keep the agent loop alive — after offline this is critical
        if not is_agent_loop_running():
            restart_agent_loop(boot_delay_sec=2)
            actions.append("agent_loop_restarted")
        elif ensure_agent_loop_running(boot_delay_sec=2):
            actions.append("agent_loop_respawned")

        # Kick a cycle if last run is overdue OR we just came back online
        db_chk = SessionLocal()
        try:
            agent_row = db_chk.query(_AgentStatus).first()
            overdue = False
            if agent_row and agent_row.last_run_at:
                gap = (datetime.utcnow() - agent_row.last_run_at.replace(tzinfo=None)).total_seconds()
                overdue = gap > settings.agent_loop_interval * 3
            elif not agent_row or not agent_row.last_run_at:
                overdue = True
            if (_was_offline or overdue or offline_now) and is_agent_loop_running():
                if settings.auto_recovery_enabled or _was_offline or offline_now:
                    await trigger_agent_cycle_now()
                    actions.append("agent_cycle_kicked")
        finally:
            db_chk.close()

        from agent.binance_client import invalidate_binance_diagnose, diagnose_binance

        # After being offline (or currently down), force a fresh Binance check
        if _was_offline or ws_down or ingest_stale:
            invalidate_binance_diagnose()
            diag = await asyncio.to_thread(diagnose_binance, True)
            actions.append(
                "binance_ok" if diag.get("market_ok") else "binance_still_down"
            )

        if ingest_stale:
            await run_all_fetchers()
            actions.append("ingestion_kicked")

        # Clear offline flag once both look healthy after recovery actions
        ws2 = get_ws_status()
        ingest2 = get_ingestion_status()
        now_ok = (
            ws2.get("status") == "connected"
            and ingest2.get("last_run_at") is not None
        )
        if _was_offline and now_ok:
            _was_offline = False
            db = SessionLocal()
            try:
                create_alert(
                    db, "success", "system", "Services Recovered",
                    "Network is back — WebSocket, market data, and Binance checks restarted automatically.",
                )
            finally:
                db.close()
            actions.append("recovered_alert")
            logger.info("Post-offline recovery complete: %s", ", ".join(actions) or "noop")
        elif actions:
            logger.info("Recovery actions: %s", ", ".join(actions))
    except Exception as e:
        logger.error("Offline recovery failed: %s", e)
        _autopilot_issues = [f"Recovery error: {e}"]


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
            _autopilot_issues.append("Binance WebSocket disconnected — recovery job will restart it")
            ensure_ws_running()

        agent = db.query(AgentStatus).first()
        if agent and agent.last_run_at:
            max_gap = timedelta(seconds=settings.agent_loop_interval * 3)
            if datetime.utcnow() - agent.last_run_at.replace(tzinfo=None) > max_gap:
                _autopilot_issues.append("Agent overdue — triggering recovery")
                if settings.auto_recovery_enabled:
                    from agent.loop import ensure_agent_loop_running, trigger_agent_cycle_now
                    ensure_agent_loop_running()
                    create_alert(db, "warning", "system", "Agent Auto-Recovery", "Agent was stuck — restarted cycle automatically.")
                    await trigger_agent_cycle_now()
        from agent.loop import ensure_agent_loop_running, is_agent_loop_running
        if not is_agent_loop_running():
            _autopilot_issues.append("Agent loop dead — respawning")
            ensure_agent_loop_running()

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
    scheduler.add_job(
        recover_after_offline,
        "interval",
        minutes=2,
        id="offline_recovery",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    if not scheduler.running:
        scheduler.start()
    logger.info("Autopilot health (15m) + offline recovery (2m) started")


def stop_autopilot_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
