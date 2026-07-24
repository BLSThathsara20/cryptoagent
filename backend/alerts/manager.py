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
    """Delete alert once user has read it — keeps DB lean."""
    alert = db.query(SystemAlert).filter(SystemAlert.id == alert_id).first()
    if not alert:
        return False
    db.delete(alert)
    db.commit()
    return True


def mark_all_read(db: Session) -> int:
    """Delete all unread alerts (user cleared inbox)."""
    count = db.query(SystemAlert).filter(SystemAlert.read.is_(False)).count()
    db.query(SystemAlert).filter(SystemAlert.read.is_(False)).delete(synchronize_session=False)
    db.commit()
    return count


def delete_read_alerts(db: Session, commit: bool = True) -> int:
    """Purge any remaining read alerts (safety net for retention)."""
    count = db.query(SystemAlert).filter(SystemAlert.read.is_(True)).delete(synchronize_session=False)
    if commit:
        db.commit()
    return count
