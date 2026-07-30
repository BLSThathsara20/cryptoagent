"""Paper trading and live trade execution via CCXT."""

import json
import logging
from datetime import datetime

import ccxt
from sqlalchemy.orm import Session

from config import settings
from db.models import AgentDecision, PaperAccount, PaperPnLHistory, AgentMemory

logger = logging.getLogger(__name__)


def _json_safe(value):
    """Convert numpy/bool/etc into JSON-serializable Python types for JSON columns."""
    return json.loads(json.dumps(value, default=str))


def _get_or_create_paper_account(db: Session) -> PaperAccount:
    """Get or initialize paper trading account."""
    account = db.query(PaperAccount).first()
    if not account:
        account = PaperAccount(
            balance=settings.starting_balance,
            initial_balance=settings.starting_balance,
            total_pnl=0.0,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
    return account


def _calculate_position_size(balance: float, entry: float, stop_loss: float) -> float:
    """Calculate position size based on max risk percent."""
    risk_amount = balance * (settings.max_risk_percent / 100)
    risk_per_unit = abs(entry - stop_loss)
    if risk_per_unit <= 0:
        return 0
    return risk_amount / risk_per_unit


def execute_paper_trade(db: Session, decision: dict) -> AgentDecision | None:
    """Simulate a paper trade and record the decision."""
    if not decision.get("stop_loss"):
        logger.error("Trade rejected: no stop loss defined")
        return None

    account = _get_or_create_paper_account(db)
    entry = float(decision["entry"])
    stop_loss = float(decision["stop_loss"])
    position_size = _calculate_position_size(account.balance, entry, stop_loss)

    if position_size <= 0:
        logger.error("Trade rejected: invalid position size")
        return None

    signals = decision.get("technical_signals")
    meta = {
        "decision_source": decision.get("decision_source") or "unknown",
        "local_model_score": decision.get("local_model_score"),
        "style": "scalp_short_hold",
        "max_hold_minutes": settings.max_hold_minutes,
        "sl_percent": settings.trade_sl_percent,
        "tp_percent": settings.trade_tp_percent,
        "min_confidence": settings.min_confidence_to_trade,
    }
    # Pack signals + meta so history modal can show strategy used
    packed_signals = _json_safe({"signals": signals, "meta": meta})

    record = AgentDecision(
        coin=decision["coin"].upper(),
        direction=decision["direction"],
        entry_price=entry,
        take_profit=float(decision["take_profit"]),
        stop_loss=stop_loss,
        confidence=float(decision.get("confidence", 0)),
        reasoning=decision.get("reasoning", ""),
        technical_signals=packed_signals,
        status="pending",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info(
        "Paper trade placed: %s %s @ %s (SL: %s, TP: %s)",
        decision["direction"],
        decision["coin"],
        entry,
        stop_loss,
        decision["take_profit"],
    )
    return record


def execute_live_trade(decision: dict) -> dict | None:
    """Execute a real trade on Binance via CCXT."""
    if not settings.live_mode:
        logger.warning("Live mode disabled — trade not executed")
        return None

    if not settings.binance_api_key or not settings.binance_secret:
        logger.error("Binance API credentials not configured")
        return None

    if not decision.get("stop_loss"):
        logger.error("Live trade rejected: no stop loss defined")
        return None

    try:
        exchange = ccxt.binance(
            {
                "apiKey": settings.binance_api_key,
                "secret": settings.binance_secret,
                "enableRateLimit": True,
            }
        )
        balance_info = exchange.fetch_balance()
        usdt_balance = balance_info.get("USDT", {}).get("free", 0)

        entry = float(decision["entry"])
        stop_loss = float(decision["stop_loss"])
        position_size = _calculate_position_size(usdt_balance, entry, stop_loss)

        symbol = f"{decision['coin']}/USDT"
        side = "buy" if decision["direction"] == "long" else "sell"

        order = exchange.create_market_order(symbol, side, position_size)
        logger.info("Live trade executed: %s", order.get("id"))
        return order

    except Exception as e:
        logger.error("Live trade failed: %s", e)
        return None


def execute_trade(db: Session, decision: dict) -> AgentDecision | None:
    """Route to paper or live execution based on settings."""
    if settings.live_mode:
        live_result = execute_live_trade(decision)
        if live_result:
            signals = decision.get("technical_signals")
            meta = {
                "decision_source": decision.get("decision_source") or "unknown",
                "local_model_score": decision.get("local_model_score"),
                "style": "scalp_short_hold",
                "max_hold_minutes": settings.max_hold_minutes,
                "sl_percent": settings.trade_sl_percent,
                "tp_percent": settings.trade_tp_percent,
                "live": True,
            }
            record = AgentDecision(
                coin=decision["coin"].upper(),
                direction=decision["direction"],
                entry_price=float(decision["entry"]),
                take_profit=float(decision["take_profit"]),
                stop_loss=float(decision["stop_loss"]),
                confidence=float(decision.get("confidence", 0)),
                reasoning=decision.get("reasoning", ""),
                technical_signals=_json_safe({"signals": signals, "meta": meta}),
                status="pending",
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return record
        return None
    return execute_paper_trade(db, decision)


def _record_trade_memory(db: Session, trade: AgentDecision, pnl: float):
    """Store a lesson from a closed trade for future agent context."""
    if trade.status == "win":
        lesson = (
            f"WIN on {trade.coin} {trade.direction}: entry ${trade.entry_price}, "
            f"TP ${trade.take_profit}, SL ${trade.stop_loss}. PnL ${pnl:.2f}. "
            f"Reasoning was: {(trade.reasoning or '')[:200]}"
        )
    else:
        lesson = (
            f"LOSS on {trade.coin} {trade.direction}: entry ${trade.entry_price}, "
            f"hit SL ${trade.stop_loss} (TP was ${trade.take_profit}). PnL ${pnl:.2f}. "
            f"Avoid similar setup when: {(trade.reasoning or '')[:200]}"
        )
    db.add(
        AgentMemory(
            coin=trade.coin,
            direction=trade.direction,
            outcome=trade.status,
            pnl=pnl,
            lesson=lesson,
        )
    )


def _finalize_close(db: Session, account: PaperAccount, trade: AgentDecision, pnl: float, reason: str):
    trade.outcome_pnl = round(pnl, 2)
    trade.closed_at = datetime.utcnow()
    if trade.status == "win":
        account.win_count += 1
    else:
        account.loss_count += 1
    account.balance += pnl
    account.total_pnl = account.balance - account.initial_balance

    peak = account.initial_balance
    if account.balance < peak:
        dd = (peak - account.balance) / peak * 100
        account.max_drawdown = max(account.max_drawdown, dd)

    db.add(PaperPnLHistory(balance=account.balance, pnl=pnl))
    _record_trade_memory(db, trade, pnl)
    from alerts.manager import create_alert

    create_alert(
        db,
        "success" if trade.status == "win" else "warning",
        "trading",
        f"Trade Closed: {trade.status.upper()} {trade.coin}",
        f"{trade.direction} · PnL ${pnl:.2f} · {reason}",
        commit=False,
    )
    db.commit()
    try:
        from agent.local_learner import label_snapshot_and_train, bump_memory_stat

        label_snapshot_and_train(db, trade, pnl)
        bump_memory_stat(db)
    except Exception as learn_err:
        logger.warning("Local learner update failed: %s", learn_err)
    logger.info(
        "Trade closed: %s %s — %s (PnL: $%.2f) [%s]",
        trade.coin,
        trade.direction,
        trade.status,
        pnl,
        reason,
    )


def check_pending_trades(db: Session):
    """Close on TP/SL, time-exit after MAX_HOLD_MINUTES, trim excess open trades."""
    from db.models import CoinPrice
    from sqlalchemy import desc

    account = _get_or_create_paper_account(db)
    max_hold = max(5, int(settings.max_hold_minutes))
    max_open = max(1, int(settings.max_open_trades))

    def _latest(symbol: str):
        return (
            db.query(CoinPrice)
            .filter(CoinPrice.symbol == symbol)
            .order_by(desc(CoinPrice.timestamp))
            .first()
        )

    def _try_close(trade: AgentDecision, force_reason: str | None = None) -> bool:
        latest_price = _latest(trade.coin)
        if not latest_price:
            return False
        price = float(latest_price.price)
        position_size = _calculate_position_size(
            account.initial_balance, trade.entry_price, trade.stop_loss
        )
        if position_size <= 0:
            return False
        risk = abs(trade.entry_price - trade.stop_loss)

        hit_tp = hit_sl = False
        if trade.direction == "long":
            hit_tp = price >= trade.take_profit
            hit_sl = price <= trade.stop_loss
        else:
            hit_tp = price <= trade.take_profit
            hit_sl = price >= trade.stop_loss

        age_min = 0.0
        if trade.created_at:
            created = trade.created_at
            if getattr(created, "tzinfo", None):
                created = created.replace(tzinfo=None)
            age_min = (datetime.utcnow() - created).total_seconds() / 60.0
        timed_out = age_min >= max_hold

        if not (hit_tp or hit_sl or timed_out or force_reason):
            return False

        if hit_tp and not force_reason:
            if trade.direction == "short":
                pnl = abs(trade.entry_price - trade.take_profit) * position_size
            else:
                pnl = abs(trade.take_profit - trade.entry_price) * position_size
            trade.status = "win"
            reason = "take_profit"
        elif hit_sl and not force_reason:
            pnl = -risk * position_size
            trade.status = "loss"
            reason = "stop_loss"
        else:
            if trade.direction == "long":
                pnl = (price - trade.entry_price) * position_size
            else:
                pnl = (trade.entry_price - price) * position_size
            trade.status = "win" if pnl >= 0 else "loss"
            reason = force_reason or f"time_exit_{int(age_min)}m"
            if trade.reasoning:
                trade.reasoning = f"{trade.reasoning} [{reason} @ ${price}]"

        _finalize_close(db, account, trade, pnl, reason)
        return True

    pending = (
        db.query(AgentDecision)
        .filter(AgentDecision.status == "pending")
        .order_by(AgentDecision.created_at.asc())
        .all()
    )
    for trade in list(pending):
        _try_close(trade)

    # Trim backlog: keep only newest max_open — market-close oldest extras
    pending = (
        db.query(AgentDecision)
        .filter(AgentDecision.status == "pending")
        .order_by(AgentDecision.created_at.asc())
        .all()
    )
    while len(pending) > max_open:
        oldest = pending.pop(0)
        _try_close(oldest, force_reason="trim_excess_open")
        pending = (
            db.query(AgentDecision)
            .filter(AgentDecision.status == "pending")
            .order_by(AgentDecision.created_at.asc())
            .all()
        )


def count_open_trades(db: Session) -> int:
    return db.query(AgentDecision).filter(AgentDecision.status == "pending").count()

