"""System alert creation and management."""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from db.models import SystemAlert

logger = logging.getLogger(__name__)


def create_alert(
    db: Session,
    level: str,
    category: str,
    title: str,
    message: str,
    commit: bool = True,
) -> SystemAlert:
    """Create a new system alert."""
    alert = SystemAlert(
        level=level,
        category=category,
        title=title,
        message=message,
    )
    db.add(alert)
    if commit:
        db.commit()
        db.refresh(alert)
    logger.info("Alert [%s] %s: %s", level, category, title)
    return alert


def get_alerts(db: Session, limit: int = 50, unread_only: bool = False) -> list[SystemAlert]:
    q = db.query(SystemAlert).order_by(desc(SystemAlert.created_at))
    if unread_only:
        q = q.filter(SystemAlert.read.is_(False))
    return q.limit(limit).all()


def get_unread_count(db: Session) -> int:
    return db.query(func.count(SystemAlert.id)).filter(SystemAlert.read.is_(False)).scalar() or 0


def mark_read(db: Session, alert_id: int) -> bool:
    alert = db.query(SystemAlert).filter(SystemAlert.id == alert_id).first()
    if not alert:
        return False
    alert.read = True
    db.commit()
    return True


def mark_all_read(db: Session) -> int:
    count = db.query(SystemAlert).filter(SystemAlert.read.is_(False)).update({"read": True})
    db.commit()
    return count


def cleanup_old_alerts(db: Session, days: int = 30):
    """Remove alerts older than N days."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    db.query(SystemAlert).filter(SystemAlert.created_at < cutoff).delete()
    db.commit()
