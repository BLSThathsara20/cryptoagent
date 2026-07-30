"""Market regime detection and trading policy when character shifts.

Handles Michael Ivanov's concern: agents trained on one market character
should not keep trading confidently into the next one.
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import desc

from config import settings
from db.models import CoinPrice, DailyLearningStat, MarketRegimeLog, AgentDecision, PaperAccount

logger = logging.getLogger(__name__)

REGIMES = ("trend_bull", "trend_bear", "chop", "high_vol", "neutral")

_last_regime: str | None = None


def _btc_change_24h(db: Session) -> float:
    rows = (
        db.query(CoinPrice)
        .filter(CoinPrice.symbol == "BTC")
        .order_by(desc(CoinPrice.timestamp))
        .limit(200)
        .all()
    )
    if len(rows) < 2:
        return 0.0
    latest = rows[0].price
    ref = rows[0].change_24h
    if ref is not None:
        return float(ref)
    cutoff = datetime.utcnow() - timedelta(hours=24)
    old = next((r for r in reversed(rows) if r.timestamp and r.timestamp.replace(tzinfo=None) <= cutoff), rows[-1])
    if not old.price:
        return 0.0
    return (latest - old.price) / old.price * 100


def _signal_stats(context: dict) -> tuple[float, float]:
    scores = [
        float(s.get("signal_score") or 0)
        for s in (context.get("technical_signals") or [])
        if isinstance(s, dict)
    ]
    if not scores:
        return 0.0, 0.0
    avg = statistics.mean(scores)
    disp = statistics.pstdev(scores) if len(scores) > 1 else 0.0
    return avg, disp


def classify_regime(context: dict, btc_change: float, fg_val: int | None, avg_signal: float, dispersion: float) -> str:
    """Tag current market character: trend / chop / high-vol / neutral."""
    fg = fg_val if fg_val is not None else 50

    if fg <= 20 or fg >= 80:
        return "high_vol"
    if dispersion >= 28 and abs(btc_change) < 1.5:
        return "chop"
    if btc_change >= 2.0 and avg_signal >= 12 and fg >= 40:
        return "trend_bull"
    if btc_change <= -2.0 and avg_signal <= -12 and fg <= 60:
        return "trend_bear"
    if dispersion >= 22 and abs(avg_signal) < 10:
        return "chop"
    return "neutral"


def get_learning_drift(db: Session) -> dict:
    """Detect when recent closed outcomes diverge from prior character."""
    days = (
        db.query(DailyLearningStat)
        .order_by(desc(DailyLearningStat.day))
        .limit(5)
        .all()
    )
    negative_streak = 0
    for d in days:
        lr = float(d.learning_rate or 0)
        if lr < settings.regime_learning_rate_negative_threshold:
            negative_streak += 1
        else:
            break

    accuracy_drop = 0.0
    if len(days) >= 2:
        recent = float(days[0].accuracy_percent or 0)
        prior = float(days[1].accuracy_percent or 0)
        if prior > 0:
            accuracy_drop = max(0.0, prior - recent)

    today_lr = float(days[0].learning_rate or 0) if days else 0.0
    drift_detected = (
        negative_streak >= settings.regime_learning_negative_days
        or accuracy_drop >= settings.regime_pause_accuracy_drop
    )

    return {
        "learning_rate_today": round(today_lr, 1),
        "negative_streak_days": negative_streak,
        "accuracy_drop_points": round(accuracy_drop, 1),
        "drift_detected": drift_detected,
    }


def _recent_drawdown(db: Session) -> float:
    account = db.query(PaperAccount).first()
    return float(account.max_drawdown or 0) if account else 0.0


def _recent_win_rate(db: Session, limit: int = 20) -> float:
    closed = (
        db.query(AgentDecision)
        .filter(AgentDecision.status.in_(["win", "loss"]))
        .order_by(desc(AgentDecision.closed_at))
        .limit(limit)
        .all()
    )
    if not closed:
        return 0.0
    wins = sum(1 for t in closed if t.status == "win")
    return wins / len(closed) * 100


def evaluate_regime_policy(db: Session, context: dict) -> dict:
    """
    Build trading policy from regime + learning drift.
    Returns size multiplier, effective min confidence, pause flag, lesson cap.
    """
    global _last_regime

    btc_change = _btc_change_24h(db)
    fg = context.get("fear_greed") or {}
    fg_val = fg.get("value") if isinstance(fg, dict) else None
    avg_signal, dispersion = _signal_stats(context)

    regime = classify_regime(context, btc_change, fg_val, avg_signal, dispersion)
    previous = _last_regime
    shifted = previous is not None and previous != regime
    _last_regime = regime

    drift = get_learning_drift(db)
    drawdown = _recent_drawdown(db)
    win_rate = _recent_win_rate(db)

    size_multiplier = 1.0
    confidence_boost = 0.0
    allow_new_trades = True
    lesson_limit = 10
    stale_lessons = False
    notes: list[str] = []

    if shifted:
        size_multiplier *= settings.regime_size_reduction_on_shift
        confidence_boost += settings.regime_min_confidence_boost_on_shift
        lesson_limit = settings.regime_lesson_cap_on_shift
        stale_lessons = True
        notes.append(f"Regime shift {previous} → {regime}: size ×{size_multiplier:.2f}, fewer stale lessons")

    if drift["drift_detected"]:
        size_multiplier *= settings.regime_size_reduction_on_drift
        confidence_boost += settings.regime_confidence_boost_on_drift
        lesson_limit = min(lesson_limit, settings.regime_lesson_cap_on_drift)
        stale_lessons = True
        notes.append(
            f"Learning drift: {drift['negative_streak_days']}d negative learning rate "
            f"or −{drift['accuracy_drop_points']:.0f}pt accuracy"
        )

    if regime == "chop":
        size_multiplier *= 0.7
        confidence_boost += 5
        notes.append("Chop regime — tighter entry bar")

    if regime == "high_vol":
        size_multiplier *= 0.6
        confidence_boost += 8
        notes.append("High-vol / extreme sentiment — reduced size")

    if regime == "trend_bear" and avg_signal > 0:
        confidence_boost += 5
        notes.append("Bear regime but bullish signals — extra skepticism")

    if drawdown >= settings.regime_drawdown_pause_pct:
        allow_new_trades = False
        notes.append(f"Drawdown {drawdown:.1f}% — pausing new entries")

    if drift["accuracy_drop_points"] >= settings.regime_pause_accuracy_drop:
        allow_new_trades = False
        notes.append("Accuracy collapse — pausing until character stabilizes")

    if win_rate > 0 and win_rate < settings.regime_min_win_rate_pct and drift["negative_streak_days"] >= 1:
        size_multiplier *= 0.5
        confidence_boost += 5
        notes.append(f"Recent win rate {win_rate:.0f}% — halving size")

    effective_min_confidence = min(95.0, settings.min_confidence_to_trade + confidence_boost)

    log = MarketRegimeLog(
        regime=regime,
        previous_regime=previous,
        shifted=shifted,
        btc_change_24h=round(btc_change, 2),
        fear_greed=fg_val,
        signal_avg=round(avg_signal, 2),
        signal_dispersion=round(dispersion, 2),
        learning_rate=drift["learning_rate_today"],
        size_multiplier=round(size_multiplier, 3),
        allow_new_trades=allow_new_trades,
        policy_notes=notes,
    )
    db.add(log)
    db.commit()

    policy = {
        "regime": regime,
        "regime_label": regime.replace("_", " ").title(),
        "previous_regime": previous,
        "regime_shifted": shifted,
        "btc_change_24h": round(btc_change, 2),
        "fear_greed": fg_val,
        "signal_avg": round(avg_signal, 2),
        "signal_dispersion": round(dispersion, 2),
        "learning_drift": drift,
        "size_multiplier": round(size_multiplier, 3),
        "min_confidence_effective": round(effective_min_confidence, 1),
        "allow_new_trades": allow_new_trades,
        "stale_lessons_downweighted": stale_lessons,
        "lesson_limit": lesson_limit,
        "policy_notes": notes,
        "recent_win_rate": round(win_rate, 1),
        "max_drawdown": round(drawdown, 1),
    }
    logger.info(
        "Regime policy: %s (shift=%s) allow=%s size×=%.2f min_conf=%.0f",
        regime, shifted, allow_new_trades, size_multiplier, effective_min_confidence,
    )
    return policy


def filter_past_lessons(lessons: list[dict], policy: dict) -> list[dict]:
    """Down-weight stale lessons after regime shift or negative learning drift."""
    limit = int(policy.get("lesson_limit") or 10)
    if policy.get("stale_lessons_downweighted"):
        return lessons[:limit]
    return lessons[:10]


def get_latest_regime(db: Session) -> dict | None:
    row = db.query(MarketRegimeLog).order_by(desc(MarketRegimeLog.created_at)).first()
    if not row:
        return None
    return {
        "regime": row.regime,
        "regime_label": row.regime.replace("_", " ").title(),
        "previous_regime": row.previous_regime,
        "regime_shifted": row.shifted,
        "btc_change_24h": row.btc_change_24h,
        "fear_greed": row.fear_greed,
        "learning_rate": row.learning_rate,
        "size_multiplier": row.size_multiplier,
        "allow_new_trades": row.allow_new_trades,
        "policy_notes": row.policy_notes or [],
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
