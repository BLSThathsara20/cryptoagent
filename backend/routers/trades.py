"""Trade history API endpoints."""

from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from config import settings
from db.session import get_db
from db.models import AgentDecision, AgentMemory, LearningFeatureSnapshot, CoinPrice
from utils.pagination import paginate_params, paginated

router = APIRouter(prefix="/api/trades", tags=["trades"])

CLOSE_TAG_RE = re.compile(r"\[([^\]]+)\]\s*$")


def _unpack_signals(raw) -> tuple[list, dict]:
    """Support legacy list signals and new {signals, meta} pack."""
    if raw is None:
        return [], {}
    if isinstance(raw, dict) and ("signals" in raw or "meta" in raw):
        signals = raw.get("signals") or []
        meta = raw.get("meta") or {}
        if isinstance(signals, dict):
            signals = [signals]
        if not isinstance(signals, list):
            signals = []
        return signals, meta if isinstance(meta, dict) else {}
    if isinstance(raw, list):
        return raw, {}
    if isinstance(raw, dict):
        return [raw], {}
    return [], {}


def _parse_close_reason(reasoning: str | None, status: str) -> str | None:
    if status == "pending":
        return None
    if not reasoning:
        return "unknown"
    m = CLOSE_TAG_RE.search(reasoning.strip())
    if not m:
        if status == "win":
            return "take_profit_or_time"
        if status == "loss":
            return "stop_loss_or_time"
        return status
    tag = m.group(1)
    if "trim_excess" in tag:
        return "trim_excess_open"
    if "time-exit" in tag or "time_exit" in tag:
        return "time_exit"
    if "take_profit" in tag:
        return "take_profit"
    if "stop_loss" in tag:
        return "stop_loss"
    return tag.split("@")[0].strip() or "closed"


def _clean_reasoning(reasoning: str | None) -> str:
    if not reasoning:
        return ""
    return CLOSE_TAG_RE.sub("", reasoning).strip()


def _strategy_label(meta: dict, reasoning: str) -> str:
    src = (meta.get("decision_source") or "").lower()
    if src.startswith("llm"):
        return "LLM scalp (selective OpenAI/Claude)"
    if src.startswith("rules"):
        if "strong" in src:
            return "Rule-based scalp (strong signal — no LLM cost)"
        if "cooldown" in src:
            return "Rule-based scalp (LLM on cooldown)"
        if "weak" in src:
            return "Rule-based / filtered"
        return "Rule-based scalp"
    if "Rule scalp" in (reasoning or "") or "Rule-based" in (reasoning or ""):
        return "Rule-based scalp"
    if "Local model" in (reasoning or ""):
        return "LLM + local model blend"
    if reasoning:
        return "LLM analysis"
    return "Unknown"


def _current_price(db: Session, symbol: str) -> float | None:
    row = (
        db.query(CoinPrice)
        .filter(CoinPrice.symbol == symbol)
        .order_by(desc(CoinPrice.timestamp))
        .first()
    )
    return float(row.price) if row else None


def _unrealized_pnl_with_account(db: Session, trade: AgentDecision, price: float | None) -> float | None:
    if trade.status != "pending" or price is None:
        return None
    from db.models import PaperAccount

    account = db.query(PaperAccount).first()
    balance = float(account.initial_balance) if account else float(settings.starting_balance)
    entry = float(trade.entry_price or 0)
    sl = float(trade.stop_loss or 0)
    risk = abs(entry - sl)
    if risk <= 0 or entry <= 0:
        return None
    risk_amount = balance * (settings.max_risk_percent / 100)
    position = risk_amount / risk
    if trade.direction == "long":
        pnl = (price - entry) * position
    else:
        pnl = (entry - price) * position
    return round(pnl, 2)


def _trade_summary(r: AgentDecision, db: Session | None = None) -> dict:
    signals, meta = _unpack_signals(r.technical_signals)
    close_reason = _parse_close_reason(r.reasoning, r.status)
    unrealized = None
    mark = None
    if db is not None and r.status == "pending":
        mark = _current_price(db, r.coin)
        unrealized = _unrealized_pnl_with_account(db, r, mark)

    return {
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
        "unrealized_pnl": unrealized,
        "mark_price": mark,
        "display_pnl": r.outcome_pnl if r.outcome_pnl is not None else unrealized,
        "pnl_kind": (
            "realized" if r.outcome_pnl is not None
            else ("unrealized" if unrealized is not None else "none")
        ),
        "close_reason": close_reason,
        "strategy": _strategy_label(meta, r.reasoning or ""),
        "decision_source": meta.get("decision_source"),
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "closed_at": r.closed_at.isoformat() if r.closed_at else None,
    }


def _trade_detail(r: AgentDecision, db: Session) -> dict:
    data = _trade_summary(r, db)
    signals, meta = _unpack_signals(r.technical_signals)
    coin_signals = [
        s for s in signals
        if isinstance(s, dict) and str(s.get("symbol", "")).upper() == str(r.coin).upper()
    ]
    if not coin_signals and signals:
        coin_signals = [signals[0]] if isinstance(signals[0], dict) else []

    entry = float(r.entry_price or 0)
    tp = float(r.take_profit or 0)
    sl = float(r.stop_loss or 0)
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    data["risk_usd_per_unit"] = round(risk, 6)
    data["reward_usd_per_unit"] = round(reward, 6)
    data["risk_reward"] = round(reward / risk, 2) if risk > 0 else None
    data["sl_percent"] = round(abs(entry - sl) / entry * 100, 3) if entry else None
    data["tp_percent"] = round(abs(tp - entry) / entry * 100, 3) if entry else None

    if r.created_at and r.closed_at:
        created, closed = r.created_at, r.closed_at
        if getattr(created, "tzinfo", None):
            created = created.replace(tzinfo=None)
        if getattr(closed, "tzinfo", None):
            closed = closed.replace(tzinfo=None)
        data["hold_seconds"] = int((closed - created).total_seconds())
    elif r.created_at and r.status == "pending":
        created = r.created_at
        if getattr(created, "tzinfo", None):
            created = created.replace(tzinfo=None)
        data["hold_seconds"] = int((datetime.utcnow() - created).total_seconds())
    else:
        data["hold_seconds"] = None

    data["entry_reason"] = _clean_reasoning(r.reasoning)
    data["technical_signals"] = signals
    data["coin_signal"] = coin_signals[0] if coin_signals else None
    data["meta"] = {
        **meta,
        "style": meta.get("style") or "scalp_short_hold",
        "max_hold_minutes": meta.get("max_hold_minutes") or settings.max_hold_minutes,
        "sl_percent_cfg": meta.get("sl_percent") or settings.trade_sl_percent,
        "tp_percent_cfg": meta.get("tp_percent") or settings.trade_tp_percent,
    }
    data["exit_plan"] = {
        "take_profit": tp,
        "stop_loss": sl,
        "time_exit_minutes": data["meta"]["max_hold_minutes"],
        "close_reason": data["close_reason"],
        "status": r.status,
    }

    snap = (
        db.query(LearningFeatureSnapshot)
        .filter(LearningFeatureSnapshot.decision_id == r.id)
        .order_by(desc(LearningFeatureSnapshot.id))
        .first()
    )
    if snap:
        data["learning_snapshot"] = {
            "features": snap.features,
            "special": snap.special,
            "special_reason": snap.special_reason,
            "outcome": snap.outcome,
            "local_score_at_label": None,
        }
    else:
        data["learning_snapshot"] = None

    mem = (
        db.query(AgentMemory)
        .filter(
            AgentMemory.coin == r.coin,
            AgentMemory.direction == r.direction,
            AgentMemory.outcome == r.status,
        )
        .order_by(desc(AgentMemory.created_at))
        .first()
    )
    # Prefer memory created near close time
    if r.closed_at and mem and mem.created_at:
        delta = abs((mem.created_at.replace(tzinfo=None) - r.closed_at.replace(tzinfo=None)).total_seconds())
        if delta > 600:
            mem = None
    data["lesson"] = mem.lesson if mem else None

    return data


@router.get("/history")
def get_trade_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    limit: int | None = Query(None, ge=1, le=200, description="Legacy alias for page_size"),
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """Paginated agent trade decisions with outcomes."""
    size = limit if limit is not None else page_size
    offset, size = paginate_params(page, size)

    query = db.query(AgentDecision)
    if status == "pending":
        query = query.filter(AgentDecision.status == "pending")
    elif status == "closed":
        query = query.filter(AgentDecision.status.in_(("win", "loss")))
    elif status in ("win", "loss", "cancelled"):
        query = query.filter(AgentDecision.status == status)

    total = query.count()
    rows = (
        query.order_by(desc(AgentDecision.created_at))
        .offset(offset)
        .limit(size)
        .all()
    )
    return paginated(
        [_trade_summary(r, db) for r in rows],
        total=total,
        page=page,
        page_size=size,
        key="trades",
    )


@router.get("/stats")
def get_trade_stats(db: Session = Depends(get_db)):
    """Aggregate trade statistics (SQL aggregates — no full table load)."""
    total = db.query(func.count(AgentDecision.id)).scalar() or 0
    pending = (
        db.query(func.count(AgentDecision.id))
        .filter(AgentDecision.status == "pending")
        .scalar()
        or 0
    )
    wins = (
        db.query(func.count(AgentDecision.id))
        .filter(AgentDecision.status == "win")
        .scalar()
        or 0
    )
    losses = (
        db.query(func.count(AgentDecision.id))
        .filter(AgentDecision.status == "loss")
        .scalar()
        or 0
    )
    total_pnl = (
        db.query(func.coalesce(func.sum(AgentDecision.outcome_pnl), 0.0))
        .filter(AgentDecision.status.in_(("win", "loss")))
        .scalar()
        or 0
    )
    closed = wins + losses
    win_rate = (wins / closed * 100) if closed > 0 else 0

    return {
        "total": total,
        "pending": pending,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "total_pnl": round(float(total_pnl), 2),
    }


@router.get("/{trade_id}")
def get_trade_detail(trade_id: int, db: Session = Depends(get_db)):
    """Full detail for a single trade (modal)."""
    row = db.query(AgentDecision).filter(AgentDecision.id == trade_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Trade not found")
    return _trade_detail(row, db)
