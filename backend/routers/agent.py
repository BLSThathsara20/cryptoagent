"""Agent status and decision API endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from config import settings
from db.session import get_db
from db.models import AgentStatus, AgentDecision, PaperAccount, PaperPnLHistory

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentSettingsUpdate(BaseModel):
    loop_interval: int | None = None
    max_risk_percent: float | None = None
    watch_coins: str | None = None
    live_mode: bool | None = None


@router.get("/status")
def get_agent_status(db: Session = Depends(get_db)):
    """Current agent status and configuration."""
    status = db.query(AgentStatus).first()
    if not status:
        return {
            "status": "idle",
            "live_mode": settings.live_mode,
            "loop_interval": settings.agent_loop_interval,
            "max_risk_percent": settings.max_risk_percent,
            "watch_coins": settings.watch_coins,
            "last_run_at": None,
        }
    return {
        "status": status.status,
        "live_mode": status.live_mode,
        "loop_interval": status.loop_interval,
        "max_risk_percent": status.max_risk_percent,
        "watch_coins": status.watch_coins,
        "last_run_at": status.last_run_at.isoformat() if status.last_run_at else None,
    }


@router.get("/last-decision")
def get_last_decision(db: Session = Depends(get_db)):
    """Most recent agent decision."""
    decision = db.query(AgentDecision).order_by(desc(AgentDecision.created_at)).first()
    if not decision:
        return None
    return {
        "id": decision.id,
        "coin": decision.coin,
        "direction": decision.direction,
        "entry_price": decision.entry_price,
        "take_profit": decision.take_profit,
        "stop_loss": decision.stop_loss,
        "confidence": decision.confidence,
        "reasoning": decision.reasoning,
        "status": decision.status,
        "outcome_pnl": decision.outcome_pnl,
        "created_at": decision.created_at.isoformat() if decision.created_at else None,
    }


@router.get("/paper-account")
def get_paper_account(db: Session = Depends(get_db)):
    """Paper trading account summary."""
    account = db.query(PaperAccount).first()
    if not account:
        return {
            "balance": settings.starting_balance,
            "initial_balance": settings.starting_balance,
            "total_pnl": 0,
            "win_count": 0,
            "loss_count": 0,
            "max_drawdown": 0,
            "win_rate": 0,
        }
    total_trades = account.win_count + account.loss_count
    win_rate = (account.win_count / total_trades * 100) if total_trades > 0 else 0
    return {
        "balance": account.balance,
        "initial_balance": account.initial_balance,
        "total_pnl": account.total_pnl,
        "win_count": account.win_count,
        "loss_count": account.loss_count,
        "max_drawdown": account.max_drawdown,
        "win_rate": round(win_rate, 1),
    }


@router.get("/pnl-history")
def get_pnl_history(db: Session = Depends(get_db)):
    """Paper trading P&L history for chart."""
    rows = (
        db.query(PaperPnLHistory)
        .order_by(PaperPnLHistory.timestamp)
        .limit(500)
        .all()
    )
    return [
        {
            "balance": r.balance,
            "pnl": r.pnl,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in rows
    ]


@router.put("/settings")
def update_agent_settings(payload: AgentSettingsUpdate, db: Session = Depends(get_db)):
    """Update agent configuration."""
    status = db.query(AgentStatus).first()
    if not status:
        status = AgentStatus()
        db.add(status)

    if payload.loop_interval is not None:
        status.loop_interval = payload.loop_interval
        settings.agent_loop_interval = payload.loop_interval
    if payload.max_risk_percent is not None:
        status.max_risk_percent = payload.max_risk_percent
        settings.max_risk_percent = payload.max_risk_percent
    if payload.watch_coins is not None:
        status.watch_coins = payload.watch_coins
        settings.watch_coins = payload.watch_coins
    if payload.live_mode is not None:
        status.live_mode = payload.live_mode
        settings.live_mode = payload.live_mode

    status.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Settings updated", "live_mode": status.live_mode}


@router.post("/run-cycle")
async def run_agent_cycle_now(db: Session = Depends(get_db)):
    """Manually trigger one agent cycle — useful to start paper trading immediately."""
    from agent.loop import trigger_agent_cycle_now
    from alerts.manager import create_alert
    create_alert(db, "info", "trading", "Manual Agent Run", "Agent cycle triggered manually from dashboard.")
    await trigger_agent_cycle_now()
    status = db.query(AgentStatus).first()
    return {
        "message": "Agent cycle completed",
        "last_run_at": status.last_run_at.isoformat() if status and status.last_run_at else None,
    }
