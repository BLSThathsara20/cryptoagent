"""System alerts API."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.session import get_db
from alerts.manager import get_alerts, get_unread_count, mark_read, mark_all_read, create_alert
from agent.binance_client import is_configured, fetch_spot_balances

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
def list_alerts(
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = False,
    db: Session = Depends(get_db),
):
    rows = get_alerts(db, limit=limit, unread_only=unread_only)
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
    """Test Binance API connection and create alert with result."""
    if not is_configured():
        create_alert(
            db, "warning", "binance", "Binance Not Configured",
            "Add BINANCE_API_KEY and BINANCE_SECRET to your .env file.",
        )
        return {"connected": False, "message": "API keys not set in .env"}

    balances = fetch_spot_balances()
    if balances is None:
        create_alert(
            db, "error", "binance", "Binance Connection Failed",
            "Could not connect. Check API key, secret, permissions (Enable Reading), and IP whitelist.",
        )
        return {"connected": False, "message": "Connection failed — check keys and permissions"}

    assets = list(balances.keys())
    total_assets = len(assets)
    create_alert(
        db, "success", "binance", "Binance Connected",
        f"Successfully connected. Found {total_assets} assets with balance: {', '.join(assets[:8])}{'...' if total_assets > 8 else ''}. "
        f"LIVE_MODE=false — paper trading active, real funds are NOT traded.",
    )
    return {
        "connected": True,
        "assets": assets,
        "message": f"Connected — {total_assets} assets found. Paper mode: no real trades.",
    }
