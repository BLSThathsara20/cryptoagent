"""Local online learner — trains day-by-day from closed trade footprints.

Not a heavy GPU model: compact feature snapshots + weight updates that
blend into future decision confidence. Ready for richer models later.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import desc

from db.models import (
    AgentDecision,
    AgentMemory,
    LearningFeatureSnapshot,
    LocalModelWeights,
    DailyLearningStat,
)

logger = logging.getLogger(__name__)

WEIGHTS_NAME = "setup_scorer_v1"
DEFAULT_WEIGHTS = {
    "bias": 0.0,
    "rsi_extreme": 0.15,
    "signal_score": 0.25,
    "fear_greed": 0.1,
    "confidence": 0.35,
    "direction_short_bias": 0.05,
}
LEARNING_STEP = 0.04


def _day_key(dt: datetime | None = None) -> str:
    return (dt or datetime.utcnow()).strftime("%Y-%m-%d")


def extract_features(context: dict, decision: dict) -> dict:
    """Compact, JSON-safe features for storage + local scoring."""
    coin = (decision.get("coin") or "").upper()
    signals = context.get("technical_signals") or []
    sig = next((s for s in signals if isinstance(s, dict) and s.get("symbol") == coin), None)
    if not sig and signals and isinstance(signals[0], dict):
        sig = signals[0]

    rsi = None
    signal_score = 0.0
    macd_trend = "neutral"
    if isinstance(sig, dict):
        rsi = sig.get("rsi")
        signal_score = float(sig.get("signal_score") or 0)
        macd = sig.get("macd") or {}
        macd_trend = macd.get("trend") or "neutral"

    fg = context.get("fear_greed") or {}
    fg_val = fg.get("value") if isinstance(fg, dict) else None

    return {
        "coin": coin,
        "direction": decision.get("direction"),
        "confidence": float(decision.get("confidence") or 0),
        "rsi": float(rsi) if rsi is not None else None,
        "rsi_extreme": 1.0 if rsi is not None and (rsi >= 70 or rsi <= 30) else 0.0,
        "signal_score": signal_score,
        "macd_trend": macd_trend,
        "fear_greed": float(fg_val) if fg_val is not None else None,
        "fear_greed_norm": (float(fg_val) - 50) / 50 if fg_val is not None else 0.0,
        "direction_short": 1.0 if decision.get("direction") == "short" else 0.0,
    }


def save_decision_snapshot(db: Session, decision_row: AgentDecision, context: dict, decision: dict):
    """Persist training footprint when a trade is opened."""
    features = extract_features(context, decision)
    snap = LearningFeatureSnapshot(
        decision_id=decision_row.id,
        coin=decision_row.coin,
        direction=decision_row.direction,
        confidence=decision_row.confidence,
        features=features,
        special=False,
    )
    db.add(snap)
    db.commit()
    return snap


def _get_weights(db: Session) -> LocalModelWeights:
    row = db.query(LocalModelWeights).filter(LocalModelWeights.name == WEIGHTS_NAME).first()
    if not row:
        row = LocalModelWeights(name=WEIGHTS_NAME, weights=dict(DEFAULT_WEIGHTS), samples=0, version=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def score_setup(db: Session, features: dict) -> float:
    """Return local model score 0-100 from current weights."""
    w = _get_weights(db).weights or DEFAULT_WEIGHTS
    conf = float(features.get("confidence") or 0) / 100.0
    rsi_x = float(features.get("rsi_extreme") or 0)
    sig = float(features.get("signal_score") or 0) / 100.0
    fg = float(features.get("fear_greed_norm") or 0)
    short_b = float(features.get("direction_short") or 0)
    raw = (
        float(w.get("bias", 0))
        + float(w.get("confidence", 0.35)) * conf
        + float(w.get("rsi_extreme", 0.15)) * rsi_x
        + float(w.get("signal_score", 0.25)) * sig
        + float(w.get("fear_greed", 0.1)) * fg
        + float(w.get("direction_short_bias", 0.05)) * short_b
    )
    # map roughly to 0-100
    return max(0.0, min(100.0, 50 + raw * 50))


def label_snapshot_and_train(db: Session, trade: AgentDecision, pnl: float):
    """When a trade closes: label snapshot, mark special cases, update local weights + daily stats."""
    snap = (
        db.query(LearningFeatureSnapshot)
        .filter(LearningFeatureSnapshot.decision_id == trade.id)
        .order_by(desc(LearningFeatureSnapshot.id))
        .first()
    )
    if not snap:
        # Late snapshot from stored decision fields
        snap = LearningFeatureSnapshot(
            decision_id=trade.id,
            coin=trade.coin,
            direction=trade.direction,
            confidence=trade.confidence,
            features={
                "coin": trade.coin,
                "direction": trade.direction,
                "confidence": trade.confidence,
                "rsi_extreme": 0.0,
                "signal_score": 0.0,
                "fear_greed_norm": 0.0,
                "direction_short": 1.0 if trade.direction == "short" else 0.0,
            },
        )
        db.add(snap)
        db.flush()

    snap.outcome = trade.status
    snap.pnl = pnl
    snap.labeled_at = datetime.utcnow()

    special = False
    reason = None
    conf = float(trade.confidence or 0)
    if trade.status == "loss" and conf >= 70:
        special = True
        reason = "High-confidence loss — important negative lesson"
    elif trade.status == "win" and conf <= 40:
        special = True
        reason = "Low-confidence win — signal may be underrated"
    elif abs(pnl or 0) >= 50:
        special = True
        reason = "Large P&L footprint"
    snap.special = special
    snap.special_reason = reason

    # Online weight update: push features toward outcome
    row = _get_weights(db)
    weights = dict(row.weights or DEFAULT_WEIGHTS)
    feats = snap.features or {}
    target = 1.0 if trade.status == "win" else 0.0
    pred = score_setup(db, feats) / 100.0
    err = target - pred
    weights["bias"] = float(weights.get("bias", 0)) + LEARNING_STEP * err
    weights["confidence"] = float(weights.get("confidence", 0.35)) + LEARNING_STEP * err * (float(feats.get("confidence") or 0) / 100)
    weights["rsi_extreme"] = float(weights.get("rsi_extreme", 0.15)) + LEARNING_STEP * err * float(feats.get("rsi_extreme") or 0)
    weights["signal_score"] = float(weights.get("signal_score", 0.25)) + LEARNING_STEP * err * (float(feats.get("signal_score") or 0) / 100)
    weights["fear_greed"] = float(weights.get("fear_greed", 0.1)) + LEARNING_STEP * err * float(feats.get("fear_greed_norm") or 0)
    weights["direction_short_bias"] = float(weights.get("direction_short_bias", 0.05)) + LEARNING_STEP * err * float(feats.get("direction_short") or 0)
    row.weights = weights
    row.samples = int(row.samples or 0) + 1
    row.version = int(row.version or 1) + 1
    row.updated_at = datetime.utcnow()

    _upsert_daily_stat(db, trade, pnl, special, reason)
    db.commit()
    logger.info("Local learner updated from trade %s (%s) samples=%s", trade.id, trade.status, row.samples)


def _upsert_daily_stat(db: Session, trade: AgentDecision, pnl: float, special: bool, reason: str | None = None):
    day = _day_key(trade.closed_at or datetime.utcnow())
    stat = db.query(DailyLearningStat).filter(DailyLearningStat.day == day).first()
    if not stat:
        stat = DailyLearningStat(day=day, notes=[])
        db.add(stat)
        db.flush()

    stat.trades_closed = int(stat.trades_closed or 0) + 1
    if trade.status == "win":
        stat.wins = int(stat.wins or 0) + 1
    elif trade.status == "loss":
        stat.losses = int(stat.losses or 0) + 1
    closed = (stat.wins or 0) + (stat.losses or 0)
    stat.accuracy_percent = round((stat.wins / closed * 100) if closed else 0.0, 1)
    stat.pnl = round(float(stat.pnl or 0) + float(pnl or 0), 2)
    stat.snapshots_labeled = int(stat.snapshots_labeled or 0) + 1
    if special:
        stat.special_events = int(stat.special_events or 0) + 1
        notes = list(stat.notes or [])
        notes.append({
            "trade_id": trade.id,
            "coin": trade.coin,
            "outcome": trade.status,
            "reason": reason or "",
        })
        stat.notes = notes[-20:]

    # learning rate = today accuracy - yesterday accuracy
    yday = (
        db.query(DailyLearningStat)
        .filter(DailyLearningStat.day < day)
        .order_by(desc(DailyLearningStat.day))
        .first()
    )
    if yday and yday.accuracy_percent is not None:
        stat.learning_rate = round(float(stat.accuracy_percent) - float(yday.accuracy_percent), 1)
    else:
        stat.learning_rate = 0.0
    stat.updated_at = datetime.utcnow()


def bump_memory_stat(db: Session):
    day = _day_key()
    stat = db.query(DailyLearningStat).filter(DailyLearningStat.day == day).first()
    if not stat:
        stat = DailyLearningStat(day=day, notes=[])
        db.add(stat)
    stat.memories_added = int(stat.memories_added or 0) + 1
    db.commit()


def get_learning_overview(db: Session, days: int = 30) -> dict:
    """One-place payload: footprints, learnings, accuracy, learning rate, local model."""
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(days=days)
    decisions = (
        db.query(AgentDecision)
        .filter(AgentDecision.created_at >= cutoff)
        .order_by(desc(AgentDecision.created_at))
        .limit(100)
        .all()
    )
    snaps = (
        db.query(LearningFeatureSnapshot)
        .filter(LearningFeatureSnapshot.created_at >= cutoff)
        .order_by(desc(LearningFeatureSnapshot.created_at))
        .limit(100)
        .all()
    )
    memories = (
        db.query(AgentMemory)
        .order_by(desc(AgentMemory.created_at))
        .limit(50)
        .all()
    )
    daily = (
        db.query(DailyLearningStat)
        .order_by(desc(DailyLearningStat.day))
        .limit(days)
        .all()
    )
    weights = _get_weights(db)

    closed = [d for d in decisions if d.status in ("win", "loss")]
    wins = sum(1 for d in closed if d.status == "win")
    accuracy = round(wins / len(closed) * 100, 1) if closed else 0.0

    labeled = [s for s in snaps if s.outcome]
    specials = [s for s in snaps if s.special]

    today = next((d for d in daily if d.day == _day_key()), None)
    learning_rate = float(today.learning_rate) if today else 0.0

    # Live today P&L from closed trades (more accurate than cached DailyLearningStat)
    today_pnl_live = 0.0
    today_wins = 0
    today_losses = 0
    today_trades = 0
    target_usd = 0.0
    target_percent = 0.0
    target_status = "in_progress"
    try:
        from analytics.insights import get_daily_targets

        targets = get_daily_targets(db, days=7)
        trow = targets.get("today") or {}
        today_pnl_live = float(trow.get("pnl") or 0)
        today_wins = int(trow.get("wins") or 0)
        today_losses = int(trow.get("losses") or 0)
        today_trades = int(trow.get("trades") or 0)
        target_usd = float(targets.get("target_usd") or 0)
        target_percent = float(targets.get("target_percent") or 0)
        target_status = trow.get("status") or "in_progress"
    except Exception:
        if today and today.pnl is not None:
            today_pnl_live = float(today.pnl)

    footprints = []
    snap_by_dec = {s.decision_id: s for s in snaps}
    for d in decisions:
        s = snap_by_dec.get(d.id)
        footprints.append({
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

    return {
        "summary": {
            "accuracy_percent": accuracy,
            "learning_rate": learning_rate,
            "closed_trades": len(closed),
            "wins": wins,
            "losses": len(closed) - wins,
            "memories": db.query(AgentMemory).count(),
            "snapshots_total": db.query(LearningFeatureSnapshot).count(),
            "snapshots_labeled": db.query(LearningFeatureSnapshot).filter(LearningFeatureSnapshot.outcome.isnot(None)).count(),
            "special_count": db.query(LearningFeatureSnapshot).filter(LearningFeatureSnapshot.special.is_(True)).count(),
            "local_model_samples": weights.samples,
            "local_model_version": weights.version,
        },
        "today": {
            "day": today.day if today else _day_key(),
            "accuracy_percent": today.accuracy_percent if today else 0,
            "learning_rate": today.learning_rate if today else 0,
            "trades_closed": today_trades or (today.trades_closed if today else 0),
            "wins": today_wins,
            "losses": today_losses,
            "memories_added": today.memories_added if today else 0,
            "special_events": today.special_events if today else 0,
            "pnl": round(today_pnl_live, 2),
            "target_usd": target_usd,
            "target_percent": target_percent,
            "target_status": target_status,
            "progress_percent": round(
                min(100.0, (today_pnl_live / target_usd * 100) if target_usd > 0 else 0.0),
                1,
            ),
        },
        "daily": [
            {
                "day": d.day,
                "accuracy_percent": d.accuracy_percent,
                "learning_rate": d.learning_rate,
                "trades_closed": d.trades_closed,
                "wins": d.wins,
                "losses": d.losses,
                "memories_added": d.memories_added,
                "snapshots_labeled": d.snapshots_labeled,
                "special_events": d.special_events,
                "pnl": d.pnl,
            }
            for d in daily
        ],
        "footprints": footprints,
        "specials": [
            {
                "decision_id": s.decision_id,
                "coin": s.coin,
                "direction": s.direction,
                "outcome": s.outcome,
                "pnl": s.pnl,
                "confidence": s.confidence,
                "special_reason": s.special_reason,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in specials[:30]
        ],
        "learnings": [
            {
                "id": m.id,
                "coin": m.coin,
                "direction": m.direction,
                "outcome": m.outcome,
                "pnl": m.pnl,
                "lesson": m.lesson,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in memories
        ],
        "local_model": {
            "name": weights.name,
            "version": weights.version,
            "samples": weights.samples,
            "weights": weights.weights,
            "updated_at": weights.updated_at.isoformat() if weights.updated_at else None,
        },
        "training": {
            "ready": labeled.__len__() >= 5,
            "labeled": len(labeled),
            "unlabeled": len(snaps) - len(labeled),
            "note": "Local weights update online on every closed trade. Snapshots are training fuel for future models.",
        },
    }
