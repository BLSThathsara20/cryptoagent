"""Trade history API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from db.session import get_db
from db.models import AgentDecision

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("/history")
def get_trade_history(
    limit: int = Query(50, ge=1, le=200),
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """All agent trade decisions with outcomes."""
    query = db.query(AgentDecision).order_by(desc(AgentDecision.created_at))
    if status:
        query = query.filter(AgentDecision.status == status)
    rows = query.limit(limit).all()
    return [
        {
            "id": r.id,
            "coin": r.coin,
            "direction": r.direction,
            "entry_price": r.entry_price,
            "take_profit": r.take_profit,
            "stop_loss": r.stop_loss,
            "confidence": r.confidence,
            "reasoning": r.reasoning,
            "status": r.status,
            "outcome_pnl": r.outcome_pnl,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "closed_at": r.closed_at.isoformat() if r.closed_at else None,
        }
        for r in rows
    ]


@router.get("/stats")
def get_trade_stats(db: Session = Depends(get_db)):
    """Aggregate trade statistics."""
    all_trades = db.query(AgentDecision).all()
    pending = sum(1 for t in all_trades if t.status == "pending")
    wins = sum(1 for t in all_trades if t.status == "win")
    losses = sum(1 for t in all_trades if t.status == "loss")
    total_pnl = sum(t.outcome_pnl or 0 for t in all_trades if t.outcome_pnl)
    closed = wins + losses
    win_rate = (wins / closed * 100) if closed > 0 else 0

    return {
        "total": len(all_trades),
        "pending": pending,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
    }
