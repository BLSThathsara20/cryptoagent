"""Portfolio and Fund Manager API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from config import settings
from db.session import get_db
from db.models import PortfolioSnapshot, FundManagerDecision
from agent.fund_manager import get_portfolio, run_fund_manager_cycle
from agent.binance_client import diagnose_binance

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/holdings")
def get_holdings(db: Session = Depends(get_db)):
    """Current fund allocation — Binance if connected, else paper."""
    portfolio = get_portfolio(db)
    diag = diagnose_binance(force=False)
    return {
        **portfolio,
        "binance_connected": bool(diag.get("account_ok")),
        "binance_market_ok": bool(diag.get("market_ok")),
        "live_mode": settings.live_mode,
        "reserve_percent": settings.fund_reserve_percent,
        "max_allocation_per_coin": settings.max_allocation_per_coin,
        "daily_profit_target_percent": settings.daily_profit_target_percent,
    }


@router.get("/fund-manager/latest")
def get_latest_fund_decision(db: Session = Depends(get_db)):
    """Most recent fund manager decision."""
    row = db.query(FundManagerDecision).order_by(desc(FundManagerDecision.created_at)).first()
    if not row:
        return None
    return {
        "id": row.id,
        "action": row.action,
        "asset": row.asset,
        "amount_usd": row.amount_usd,
        "reasoning": row.reasoning,
        "portfolio_total": row.portfolio_total,
        "target_daily_profit": row.target_daily_profit,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/fund-manager/history")
def get_fund_decision_history(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Fund manager decision history."""
    rows = (
        db.query(FundManagerDecision)
        .order_by(desc(FundManagerDecision.created_at))
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "action": r.action,
            "asset": r.asset,
            "amount_usd": r.amount_usd,
            "reasoning": r.reasoning,
            "portfolio_total": r.portfolio_total,
            "target_daily_profit": r.target_daily_profit,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/fund-manager/run")
def trigger_fund_manager(db: Session = Depends(get_db)):
    """Manually trigger fund manager analysis cycle."""
    return run_fund_manager_cycle(db)


@router.get("/snapshots")
def get_portfolio_snapshots(
    limit: int = Query(24, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Historical portfolio snapshots for charting."""
    rows = (
        db.query(PortfolioSnapshot)
        .order_by(desc(PortfolioSnapshot.created_at))
        .limit(limit)
        .all()
    )
    return [
        {
            "total_usd": r.total_usd,
            "stable_usd": r.stable_usd,
            "crypto_usd": r.crypto_usd,
            "available_usd": r.available_usd,
            "source": r.source,
            "timestamp": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reversed(rows)
    ]
