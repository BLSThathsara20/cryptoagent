"""System status, health, data pipeline, and agent capabilities API."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, text

from config import settings
from db.session import get_db
from db.models import (
    CoinPrice,
    MarketDominance,
    OrderBookEntry,
    LiveTrade,
    Liquidation,
    LongShortRatio,
    FearGreedIndex,
    AgentDecision,
    AgentStatus,
    AgentMemory,
    PaperAccount,
)
from agent.loop import is_agent_loop_running

router = APIRouter(prefix="/api/system", tags=["system"])


def _last_timestamp(db: Session, model, column="timestamp"):
    col = getattr(model, column)
    return db.query(func.max(col)).scalar()


def _count_since(db: Session, model, hours: int = 24):
    since = datetime.utcnow() - timedelta(hours=hours)
    col = getattr(model, "timestamp", None) or getattr(model, "created_at")
    return db.query(func.count(model.id)).filter(col >= since).scalar() or 0


@router.get("/status")
def get_system_status(db: Session = Depends(get_db)):
    """Full system status for Settings dashboard."""
    from data.ingestion import get_ingestion_status
    from data.binance_ws import get_ws_status
    from data.retention import get_maintenance_status, get_database_stats
    from data.backup import get_backup_status
    from autopilot.scheduler import get_autopilot_status

    # DB connectivity
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    ingestion = get_ingestion_status()
    ws = get_ws_status()
    agent_row = db.query(AgentStatus).first()
    paper = db.query(PaperAccount).first()
    memory_count = db.query(func.count(AgentMemory.id)).scalar() or 0

    data_pipeline = [
        {
            "name": "CoinGecko Prices",
            "status": "active" if _last_timestamp(db, CoinPrice) else "waiting",
            "last_update": _last_timestamp(db, CoinPrice),
            "records_24h": _count_since(db, CoinPrice),
            "interval": "60s",
        },
        {
            "name": "Market Dominance",
            "status": "active" if _last_timestamp(db, MarketDominance) else "waiting",
            "last_update": _last_timestamp(db, MarketDominance),
            "records_24h": _count_since(db, MarketDominance),
            "interval": "60s",
        },
        {
            "name": "Fear & Greed Index",
            "status": "active" if _last_timestamp(db, FearGreedIndex) else "waiting",
            "last_update": _last_timestamp(db, FearGreedIndex),
            "records_24h": _count_since(db, FearGreedIndex),
            "interval": "60s",
        },
        {
            "name": "Binance WebSocket",
            "status": ws.get("status", "unknown"),
            "last_update": ws.get("last_message_at"),
            "records_24h": _count_since(db, LiveTrade),
            "interval": "real-time",
        },
        {
            "name": "Order Book",
            "status": "active" if _last_timestamp(db, OrderBookEntry) else "waiting",
            "last_update": _last_timestamp(db, OrderBookEntry),
            "records_24h": _count_since(db, OrderBookEntry),
            "interval": "real-time",
        },
        {
            "name": "Coinglass (L/S + Liquidations)",
            "status": "active" if settings.coinglass_api_key and _last_timestamp(db, LongShortRatio) else (
                "needs_api_key" if not settings.coinglass_api_key else "waiting"
            ),
            "last_update": _last_timestamp(db, LongShortRatio),
            "records_24h": _count_since(db, Liquidation),
            "interval": "60s",
        },
    ]

    def _iso(dt):
        if not dt:
            return None
        if isinstance(dt, str):
            return dt
        return dt.isoformat()

    for item in data_pipeline:
        item["last_update"] = _iso(item["last_update"])

    capabilities = _build_capabilities(db, memory_count)

    return {
        "health": {
            "status": "healthy" if db_ok else "degraded",
            "database": "connected" if db_ok else "disconnected",
            "backend": "running",
            "uptime_note": "Container uptime — see Docker",
        },
        "links": {
            "api_docs": "/docs",
            "health": "/health",
            "openapi": "/openapi.json",
        },
        "configuration": {
            "live_mode": agent_row.live_mode if agent_row else settings.live_mode,
            "paper_balance": paper.balance if paper else settings.starting_balance,
            "agent_interval_sec": agent_row.loop_interval if agent_row else settings.agent_loop_interval,
            "max_risk_percent": agent_row.max_risk_percent if agent_row else settings.max_risk_percent,
            "watch_coins": (agent_row.watch_coins if agent_row else settings.watch_coins).split(","),
            "llm_configured": settings.llm_configured,
            "llm_provider": settings.llm_provider,
            "llm_model": settings.active_llm_label,
            "llm_monthly_budget_usd": settings.llm_monthly_budget_usd,
            "binance_configured": bool(settings.binance_api_key and settings.binance_secret),
            "coinglass_configured": bool(settings.coinglass_api_key),
        },
        "data_pipeline": data_pipeline,
        "ingestion_scheduler": ingestion,
        "agent": {
            "status": agent_row.status if agent_row else "idle",
            "loop_running": is_agent_loop_running(),
            "last_run_at": _iso(agent_row.last_run_at if agent_row else None),
            "decisions_total": db.query(func.count(AgentDecision.id)).scalar() or 0,
            "decisions_24h": _count_since(db, AgentDecision, hours=24),
            "memories_learned": memory_count,
        },
        "capabilities": capabilities,
        "automation_level": _automation_level(agent_row),
        "database": get_database_stats(db),
        "maintenance": get_maintenance_status(),
        "backup": get_backup_status(),
        "autopilot": get_autopilot_status(db),
    }


@router.get("/pulse")
def get_system_pulse(db: Session = Depends(get_db)):
    """Lightweight live/offline + agent stage + data saved (for the top bar)."""
    from data.connectivity import build_live_pulse
    return build_live_pulse(db)


@router.post("/recover")
async def recover_services():
    """
    Kick WebSocket + Binance diagnose + ingestion after coming back online.
    Safe to call from the UI when the browser fires the `online` event.
    """
    from autopilot.scheduler import recover_after_offline
    await recover_after_offline()
    from data.binance_ws import get_ws_status
    from data.ingestion import get_ingestion_status
    from agent.binance_client import diagnose_binance
    from agent.binance_client import diagnose_binance
    from agent.loop import is_agent_loop_running
    return {
        "ok": True,
        "websocket": get_ws_status(),
        "ingestion": get_ingestion_status(),
        "binance": diagnose_binance(cache_only=True),
        "agent_loop_running": is_agent_loop_running(),
    }


def _build_capabilities(db: Session, memory_count: int) -> dict:
    """Honest map of what the agent can do today vs planned."""
    return {
        "active": [
            {"id": "market_data", "label": "Collect market data 24/7", "detail": "CoinGecko, Binance WS, Fear & Greed every 60s"},
            {"id": "technical", "label": "Technical analysis", "detail": "RSI, MACD, volume spikes, order book imbalance"},
            {"id": "paper_trade", "label": "Paper trading", "detail": f"Virtual ${settings.starting_balance:,.0f} account with P&L tracking"},
            {"id": "risk_mgmt", "label": "Risk management", "detail": f"Max {settings.max_risk_percent}% per trade, mandatory stop loss"},
            {"id": "auto_loop", "label": "Autonomous decision loop", "detail": f"Runs every {settings.agent_loop_interval}s without user input"},
            {"id": "learning_memory", "label": "Trade memory", "detail": f"{memory_count} lessons stored from past outcomes"},
            {"id": "fund_manager", "label": "Fund Manager Agent", "detail": "Tracks where funds are, reserve %, concentration limits, daily profit target"},
            {"id": "data_retention", "label": "Auto data cleanup", "detail": f"Deletes old WS/order book after {settings.retain_orderbook_days}d, prices after {settings.retain_coin_prices_days}d"},
        ],
        "conditional": [
            {
                "id": "binance_funds",
                "label": "Live Binance fund view",
                "enabled": bool(settings.binance_api_key and settings.binance_secret),
                "detail": "Add BINANCE keys — Fund Manager reads real spot balances",
            },
            {
                "id": "llm_brain",
                "label": "AI reasoning (OpenAI / Claude)",
                "enabled": settings.llm_configured,
                "detail": f"Provider: {settings.active_llm_label}. Set OPENAI_API_KEY or CLAUDE_API_KEY in .env",
            },
            {
                "id": "coinglass",
                "label": "Liquidations & long/short ratios",
                "enabled": bool(settings.coinglass_api_key),
                "detail": "Add COINGLASS_API_KEY — explains empty Long/Short widget",
            },
            {
                "id": "live_trading",
                "label": "Live Binance trading",
                "enabled": settings.live_mode and bool(settings.binance_api_key),
                "detail": "Requires BINANCE keys + LIVE_MODE=true",
            },
        ],
        "roadmap": [
            {"id": "daily_retrain", "label": "Daily strategy retraining", "status": "planned", "detail": "Analyze win/loss patterns nightly and adjust weights"},
            {"id": "multi_agent", "label": "Multi-agent coordination", "status": "in progress", "detail": "Fund Manager + Trading Agent run each cycle — more agents coming"},
            {"id": "llm_budget", "label": "Monthly AI budget cap", "status": "active", "detail": "Spend tracked on Agent page; rule-based fallback when budget exceeded"},
            {"id": "openai_gemini", "label": "Multi-provider LLM support", "status": "planned", "detail": "OpenAI / Gemini as cheaper alternatives"},
        ],
    }


def _automation_level(agent_row) -> dict:
    live = agent_row.live_mode if agent_row else settings.live_mode
    has_llm = settings.llm_configured
    has_binance = bool(settings.binance_api_key and settings.binance_secret)

    if live and has_binance and has_llm:
        level, pct, desc = "Full Auto (Live)", 85, "Agent trades real money on Binance with AI + learning"
    elif live and has_binance:
        level, pct, desc = "Semi-Auto (Live)", 65, "Live trading on rules — add LLM for smarter decisions"
    elif has_llm:
        level, pct, desc = "Auto Paper + AI", 55, "Fully autonomous paper trading with AI reasoning"
    else:
        level, pct, desc = "Auto Paper (Rules)", 35, "Autonomous paper trading — add LLM + Binance keys to go further"

    return {"level": level, "percent": pct, "description": desc}


@router.get("/memories")
def get_agent_memories(limit: int = 20, db: Session = Depends(get_db)):
    """Recent lessons learned from trade outcomes."""
    rows = (
        db.query(AgentMemory)
        .order_by(desc(AgentMemory.created_at))
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "coin": r.coin,
            "outcome": r.outcome,
            "lesson": r.lesson,
            "pnl": r.pnl,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
