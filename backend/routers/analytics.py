"""Analytics and insights API."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db.session import get_db
from analytics.insights import (
    get_full_insights,
    get_daily_pnl,
    get_daily_targets,
    get_wealth_growth,
    get_wealth_predictions,
    get_learnings,
    get_trading_overview,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview")
def analytics_overview(db: Session = Depends(get_db)):
    """Full insights payload for the Insights page."""
    return get_full_insights(db)


@router.get("/daily-pnl")
def daily_pnl(days: int = Query(30, ge=7, le=90), db: Session = Depends(get_db)):
    return get_daily_pnl(db, days)


@router.get("/daily-targets")
def daily_targets(days: int = Query(30, ge=7, le=90), db: Session = Depends(get_db)):
    """Today's daily profit target progress + historical hit/miss."""
    return get_daily_targets(db, days)


@router.get("/wealth")
def wealth_growth(days: int = Query(30, ge=7, le=90), db: Session = Depends(get_db)):
    return get_wealth_growth(db, days)


@router.get("/predictions")
def predictions(db: Session = Depends(get_db)):
    return get_wealth_predictions(db)


@router.get("/learnings")
def learnings(days: int = Query(30, ge=7, le=90), db: Session = Depends(get_db)):
    return get_learnings(db, days)


@router.get("/next-action")
def agent_next_action(db: Session = Depends(get_db)):
    from analytics.insights import get_agent_next_action
    return get_agent_next_action(db)


@router.get("/trading")
def trading_overview(db: Session = Depends(get_db)):
    return get_trading_overview(db)
