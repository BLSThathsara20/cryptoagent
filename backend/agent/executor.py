"""Paper trading and live trade execution via CCXT."""

import logging
from datetime import datetime

import ccxt
from sqlalchemy.orm import Session

from config import settings
from db.models import AgentDecision, PaperAccount, PaperPnLHistory, AgentMemory

logger = logging.getLogger(__name__)


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

    record = AgentDecision(
        coin=decision["coin"].upper(),
        direction=decision["direction"],
        entry_price=entry,
        take_profit=float(decision["take_profit"]),
        stop_loss=stop_loss,
        confidence=float(decision.get("confidence", 0)),
        reasoning=decision.get("reasoning", ""),
        technical_signals=decision.get("technical_signals"),
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
            record = AgentDecision(
                coin=decision["coin"].upper(),
                direction=decision["direction"],
                entry_price=float(decision["entry"]),
                take_profit=float(decision["take_profit"]),
                stop_loss=float(decision["stop_loss"]),
                confidence=float(decision.get("confidence", 0)),
                reasoning=decision.get("reasoning", ""),
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


def check_pending_trades(db: Session):
    """Check pending paper trades against current prices and close if TP/SL hit."""
    from db.models import CoinPrice
    from sqlalchemy import desc

    pending = db.query(AgentDecision).filter(AgentDecision.status == "pending").all()
    account = _get_or_create_paper_account(db)

    for trade in pending:
        latest_price = (
            db.query(CoinPrice)
            .filter(CoinPrice.symbol == trade.coin)
            .order_by(desc(CoinPrice.timestamp))
            .first()
        )
        if not latest_price:
            continue

        price = latest_price.price
        hit_tp = hit_sl = False

        if trade.direction == "long":
            hit_tp = price >= trade.take_profit
            hit_sl = price <= trade.stop_loss
        else:
            hit_tp = price <= trade.take_profit
            hit_sl = price >= trade.stop_loss

        if not (hit_tp or hit_sl):
            continue

        risk = abs(trade.entry_price - trade.stop_loss)
        position_size = _calculate_position_size(
            account.initial_balance, trade.entry_price, trade.stop_loss
        )

        if hit_tp:
            pnl = abs(trade.take_profit - trade.entry_price) * position_size
            if trade.direction == "short":
                pnl = abs(trade.entry_price - trade.take_profit) * position_size
            trade.status = "win"
            account.win_count += 1
        else:
            pnl = -risk * position_size
            trade.status = "loss"
            account.loss_count += 1

        trade.outcome_pnl = round(pnl, 2)
        trade.closed_at = datetime.utcnow()
        account.balance += pnl
        account.total_pnl = account.balance - account.initial_balance

        peak = account.initial_balance
        if account.balance < peak:
            dd = (peak - account.balance) / peak * 100
            account.max_drawdown = max(account.max_drawdown, dd)

        db.add(
            PaperPnLHistory(
                balance=account.balance,
                pnl=pnl,
            )
        )
        _record_trade_memory(db, trade, pnl)
        from alerts.manager import create_alert
        create_alert(
            db,
            "success" if trade.status == "win" else "warning",
            "trading",
            f"Trade Closed: {trade.status.upper()} {trade.coin}",
            f"{trade.direction} · PnL ${pnl:.2f} · Lesson saved to agent memory.",
            commit=False,
        )
        db.commit()
        logger.info("Trade closed: %s %s — %s (PnL: $%.2f)", trade.coin, trade.direction, trade.status, pnl)
