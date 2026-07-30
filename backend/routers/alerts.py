"""System alerts API."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.session import get_db
from alerts.manager import get_alerts, get_unread_count, mark_read, mark_all_read, create_alert
from config import settings

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    limit: int | None = Query(None, ge=1, le=200, description="Legacy alias for page_size"),
    unread_only: bool = False,
    db: Session = Depends(get_db),
):
    size = limit if limit is not None else page_size
    from utils.pagination import paginate_params, page_meta
    from db.models import SystemAlert
    from sqlalchemy import desc

    offset, size = paginate_params(page, size)
    q = db.query(SystemAlert)
    if unread_only:
        q = q.filter(SystemAlert.read.is_(False))
    total = q.count()
    rows = q.order_by(desc(SystemAlert.created_at)).offset(offset).limit(size).all()
    return {
        "unread_count": get_unread_count(db),
        "alerts": [
            {
                "id": r.id,
                "level": r.level,
                "category": r.category,
                "title": r.title,
                "message": r.message,
                "read": r.read,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        **page_meta(total, page, size),
    }


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db)):
    return {"count": get_unread_count(db)}


@router.post("/{alert_id}/read")
def read_alert(alert_id: int, db: Session = Depends(get_db)):
    ok = mark_read(db, alert_id)
    return {"ok": ok}


@router.post("/read-all")
def read_all_alerts(db: Session = Depends(get_db)):
    count = mark_all_read(db)
    return {"deleted": count}


@router.post("/test-binance")
def test_binance_connection(db: Session = Depends(get_db)):
    """Test Binance market + account API and create alert with result."""
    from agent.binance_client import diagnose_binance

    diag = diagnose_binance(force=True)
    if not diag.get("configured"):
        create_alert(
            db, "warning", "binance", "Binance Not Configured",
            "Add BINANCE_API_KEY and BINANCE_SECRET to your .env file. Public market data still works.",
        )
        return {"connected": False, "market_ok": diag.get("market_ok"), **diag}

    if diag.get("account_ok"):
        create_alert(
            db, "success", "binance", "Binance Connected",
            f"{diag.get('message')}. LIVE_MODE={str(settings.live_mode).lower()} — "
            f"{'real funds can trade' if settings.live_mode else 'paper only, real funds NOT traded'}.",
        )
        return {"connected": True, **diag}

    # Market may still be OK while account fails (-2015)
    level = "warning" if diag.get("market_ok") and not settings.live_mode else "error"
    create_alert(
        db, level, "binance", "Binance Account API Issue",
        diag.get("hint") or diag.get("message") or "Account check failed",
    )
    return {"connected": False, **diag}
