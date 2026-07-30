"""Lightweight connectivity / live-pulse helpers (does not block trading decisions)."""

import time
from datetime import datetime, timedelta

from sqlalchemy import func

from config import settings
from data.binance_ws import get_ws_status
from data.ingestion import get_ingestion_status
from data.retention import get_database_stats
from agent.binance_client import diagnose_binance
from agent.loop import is_agent_loop_running
from agent.brain import get_llm_skip_meta
from agent.llm_usage import get_current_month_spend
from db.models import AgentStatus, AgentDecision, AgentMemory, LearningFeatureSnapshot
from analytics.insights import get_daily_targets


# If no WS message / ingest for this long → treat market feed as offline
WS_STALE_SEC = 45
INGEST_STALE_SEC = 180

_db_stats_cache: dict | None = None
_db_stats_at: float = 0
_progress_cache: dict | None = None
_progress_at: float = 0


def _age_seconds(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        ts = datetime.fromisoformat(iso.replace("Z", ""))
        return max(0.0, (datetime.utcnow() - ts).total_seconds())
    except Exception:
        return None


def _cached_db_stats(db) -> dict:
    global _db_stats_cache, _db_stats_at
    now = time.time()
    if _db_stats_cache and now - _db_stats_at < 30:
        return _db_stats_cache
    _db_stats_cache = get_database_stats(db)
    _db_stats_at = now
    return _db_stats_cache


def _cached_progress(db) -> dict:
    """Heavier progress fields — refresh every 15s so pulse stays snappy."""
    global _progress_cache, _progress_at
    now = time.time()
    if _progress_cache and now - _progress_at < 15:
        return _progress_cache

    progress = {
        "target_usd": 0.0,
        "target_percent": settings.daily_profit_target_percent,
        "today_pnl": 0.0,
        "progress_percent": 0.0,
        "target_status": "in_progress",
        "open_trades": 0,
        "max_open": settings.max_open_trades,
        "max_hold_minutes": settings.max_hold_minutes,
        "accuracy_percent": 0.0,
        "memories": 0,
        "snapshots": 0,
        "llm_spent_usd": 0.0,
        "llm_budget_usd": settings.llm_monthly_budget_usd,
        "llm_mode": settings.llm_mode,
        "llm_skip": get_llm_skip_meta().get("last_skip_reason"),
    }
    try:
        targets = get_daily_targets(db, days=7)
        today = targets.get("today") or {}
        progress["target_usd"] = float(targets.get("target_usd") or 0)
        progress["target_percent"] = float(
            targets.get("target_percent") or settings.daily_profit_target_percent
        )
        progress["today_pnl"] = float(today.get("pnl") or 0)
        progress["progress_percent"] = float(today.get("progress_percent") or 0)
        progress["target_status"] = today.get("status") or "in_progress"
    except Exception:
        pass

    try:
        progress["open_trades"] = (
            db.query(func.count(AgentDecision.id))
            .filter(AgentDecision.status == "pending")
            .scalar()
            or 0
        )
        # Cheap win-rate: only last 100 closed trades
        closed = (
            db.query(AgentDecision.status)
            .filter(AgentDecision.status.in_(("win", "loss")))
            .order_by(AgentDecision.id.desc())
            .limit(100)
            .all()
        )
        if closed:
            wins = sum(1 for d in closed if d.status == "win")
            progress["accuracy_percent"] = round(wins / len(closed) * 100, 1)
        progress["memories"] = db.query(func.count(AgentMemory.id)).scalar() or 0
        progress["snapshots"] = (
            db.query(func.count(LearningFeatureSnapshot.id)).scalar() or 0
        )
        progress["llm_spent_usd"] = float(get_current_month_spend(db) or 0)
    except Exception:
        pass

    _progress_cache = progress
    _progress_at = now
    return progress


def build_live_pulse(db) -> dict:
    """
    Compact status payload for the UI.
    Must stay fast — polled every ~2s. No network I/O on this path.
    """
    ws = get_ws_status()
    ingest = get_ingestion_status()
    # Never hit Binance from pulse — use last cached diagnose only
    binance = diagnose_binance(cache_only=True)
    db_stats = _cached_db_stats(db)

    ws_age = _age_seconds(ws.get("last_message_at"))
    ingest_age = _age_seconds(ingest.get("last_run_at"))

    ws_live = bool(ws.get("socket_connected")) and (ws_age is not None and ws_age < WS_STALE_SEC)
    ingest_live = ingest_age is not None and ingest_age < INGEST_STALE_SEC
    market_ok = bool(binance.get("market_ok")) and not binance.get("pending")
    # LIVE if market feeds are flowing OR Binance public market is reachable
    online = ws_live or ingest_live or market_ok
    market_live = market_ok and (ws_live or ingest_live)

    agent_row = db.query(AgentStatus).first()
    cycle = (agent_row.status if agent_row else "idle") or "idle"
    loop_on = is_agent_loop_running()
    interval_sec = int(agent_row.loop_interval) if agent_row and agent_row.loop_interval else 300
    last_run_at = agent_row.last_run_at if agent_row else None
    next_run_at = None
    next_run_in_sec = None
    if last_run_at and loop_on:
        created = last_run_at
        if getattr(created, "tzinfo", None):
            created = created.replace(tzinfo=None)
        nxt = created.timestamp() + interval_sec
        remaining = int(nxt - datetime.utcnow().timestamp())
        next_run_in_sec = max(0, remaining)
        next_run_at = (created + timedelta(seconds=interval_sec)).isoformat()
    elif loop_on and not last_run_at:
        next_run_in_sec = 30
        next_run_at = None

    stage_map = {
        "preparing": "Preparing to decide",
        "analysing": "Reading market",
        "deciding": "Making decision",
        "executing": "Placing trade",
        "running": "Placing trade",
        "monitoring": "Watching market",
        "idle": "Watching market",
    }
    if not loop_on:
        stage_label = "Agent stopped"
        stage = "stopped"
    elif not online and cycle in ("idle", "monitoring"):
        # Keep stage as monitoring so UI countdown still ticks (not "busy")
        stage = "monitoring"
        stage_label = "Watching market (cached data)"
    else:
        stage = cycle if cycle in stage_map else "monitoring"
        stage_label = stage_map.get(stage, "Working")

    counts = db_stats.get("table_counts") or {}
    rows = sum(int(v or 0) for v in counts.values())
    size_mb = float(db_stats.get("database_size_mb") or 0)
    progress = _cached_progress(db)

    return {
        "online": online,
        "network": "live" if online else "offline",
        "using_cached_data": not online,
        "agent": {
            "loop_running": loop_on,
            "stage": stage,
            "label": stage_label,
            "last_run_at": last_run_at.isoformat() if last_run_at else None,
            "interval_sec": interval_sec,
            "next_run_at": next_run_at,
            "next_run_in_sec": next_run_in_sec,
            "live_mode": bool(agent_row.live_mode) if agent_row else False,
        },
        "feeds": {
            "websocket": "live" if ws_live else ("stale" if ws.get("socket_connected") else "offline"),
            "ingestion": "live" if ingest_live else "stale",
            "ws_messages": ws.get("messages_received", 0),
            "last_ws_at": ws.get("last_message_at"),
            "last_ingest_at": ingest.get("last_run_at"),
        },
        "binance": {
            "market": "ok" if binance.get("market_ok") else "down",
            "account": (
                "ok" if binance.get("account_ok")
                else ("not_configured" if not binance.get("configured") else "error")
            ),
            "code": binance.get("code"),
            "message": binance.get("message") or "",
            "hint": binance.get("hint") or "",
            "assets": binance.get("assets", 0),
        },
        "data": {
            "size_mb": size_mb,
            "rows": rows,
            "tables": counts,
        },
        "progress": progress,
        "checked_at": datetime.utcnow().isoformat(),
    }
