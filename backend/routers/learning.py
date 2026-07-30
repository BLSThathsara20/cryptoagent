"""Learning Hub API — decision footprints, accuracy, local model, news."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, nulls_last

from db.session import get_db
from db.models import MarketNews, AgentDecision, AgentMemory, LearningFeatureSnapshot
from agent.local_learner import get_learning_overview, score_setup
from utils.pagination import paginate_params, paginated

router = APIRouter(prefix="/api/learning", tags=["learning"])


@router.get("/overview")
def learning_overview(
    days: int = Query(30, ge=7, le=90),
    preview: int = Query(20, ge=5, le=50),
    db: Session = Depends(get_db),
):
    """Summary + short previews (use /footprints, /lessons, /news for full pages)."""
    data = get_learning_overview(db, days=days)
    # Cap list payloads so overview stays light as rows grow
    data["footprints"] = (data.get("footprints") or [])[:preview]
    data["learnings"] = (data.get("learnings") or [])[:preview]
    data["specials"] = (data.get("specials") or [])[:preview]
    data["preview_size"] = preview
    return data


@router.get("/footprints")
def list_footprints(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    special_only: bool = False,
    db: Session = Depends(get_db),
):
    offset, size = paginate_params(page, page_size)
    q = db.query(AgentDecision)
    if special_only:
        special_ids = (
            db.query(LearningFeatureSnapshot.decision_id)
            .filter(LearningFeatureSnapshot.special.is_(True))
            .subquery()
        )
        q = q.filter(AgentDecision.id.in_(special_ids))
    total = q.count()
    rows = q.order_by(desc(AgentDecision.created_at)).offset(offset).limit(size).all()

    snaps = (
        db.query(LearningFeatureSnapshot)
        .filter(LearningFeatureSnapshot.decision_id.in_([r.id for r in rows]))
        .all()
    ) if rows else []
    snap_by_dec = {s.decision_id: s for s in snaps}

    items = []
    for d in rows:
        s = snap_by_dec.get(d.id)
        items.append({
            "id": d.id,
            "coin": d.coin,
            "direction": d.direction,
            "confidence": d.confidence,
            "status": d.status,
            "outcome_pnl": d.outcome_pnl,
            "reasoning": (d.reasoning or "")[:280],
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "closed_at": d.closed_at.isoformat() if d.closed_at else None,
            "special": bool(s.special) if s else False,
            "special_reason": s.special_reason if s else None,
            "has_snapshot": s is not None,
            "local_score": score_setup(db, s.features) if s and s.features else None,
        })
    return paginated(items, total=total, page=page, page_size=size, key="items")


@router.get("/lessons")
def list_lessons(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    offset, size = paginate_params(page, page_size)
    q = db.query(AgentMemory)
    total = q.count()
    rows = q.order_by(desc(AgentMemory.created_at)).offset(offset).limit(size).all()
    items = [
        {
            "id": m.id,
            "coin": m.coin,
            "direction": m.direction,
            "outcome": m.outcome,
            "pnl": m.pnl,
            "lesson": m.lesson,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in rows
    ]
    return paginated(items, total=total, page=page, page_size=size, key="items")


@router.get("/news")
def list_news(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    limit: int | None = Query(None, ge=1, le=100, description="Legacy alias for page_size"),
    db: Session = Depends(get_db),
):
    size = limit if limit is not None else page_size
    offset, size = paginate_params(page, size)
    q = db.query(MarketNews)
    total = q.count()
    rows = (
        q.order_by(nulls_last(desc(MarketNews.published_at)), desc(MarketNews.created_at))
        .offset(offset)
        .limit(size)
        .all()
    )
    items = [
        {
            "id": r.id,
            "title": r.title,
            "url": r.url,
            "source": r.source,
            "categories": r.categories,
            "currencies": r.currencies,
            "published_at": r.published_at.isoformat() if r.published_at else None,
        }
        for r in rows
    ]
    return paginated(items, total=total, page=page, page_size=size, key="items")
