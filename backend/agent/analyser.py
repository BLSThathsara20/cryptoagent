"""Reads DB and builds structured market context for the AI agent."""

import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from config import settings
from db.models import (
    CoinPrice,
    MarketDominance,
    FearGreedIndex,
    LongShortRatio,
    Liquidation,
    OrderBookEntry,
    AgentMemory,
)
from agent.signals import analyse_symbol, get_order_book_imbalance

logger = logging.getLogger(__name__)


def _latest_prices(db: Session, limit: int = 20) -> list[dict]:
    """Get latest price for each of top coins."""
    subq = (
        db.query(
            CoinPrice.symbol,
            func.max(CoinPrice.timestamp).label("max_ts"),
        )
        .group_by(CoinPrice.symbol)
        .subquery()
    )
    coins = (
        db.query(CoinPrice)
        .join(subq, (CoinPrice.symbol == subq.c.symbol) & (CoinPrice.timestamp == subq.c.max_ts))
        .filter(CoinPrice.timestamp >= datetime.utcnow() - timedelta(hours=1))
        .order_by(CoinPrice.rank)
        .limit(limit)
        .all()
    )
    results = []
    seen = set()
    for c in coins:
        if c.symbol not in seen:
            seen.add(c.symbol)
            results.append(
                {
                    "symbol": c.symbol,
                    "name": c.name,
                    "price": c.price,
                    "change_24h": c.change_24h,
                    "volume_24h": c.volume_24h,
                    "market_cap": c.market_cap,
                    "rank": c.rank,
                }
            )
    return results[:limit]


def _latest_dominance(db: Session) -> dict:
    row = db.query(MarketDominance).order_by(desc(MarketDominance.timestamp)).first()
    if not row:
        return {}
    return {
        "btc_dominance": row.btc_dominance,
        "eth_dominance": row.eth_dominance,
        "total_market_cap": row.total_market_cap,
    }


def _latest_fear_greed(db: Session) -> dict:
    row = db.query(FearGreedIndex).order_by(desc(FearGreedIndex.timestamp)).first()
    if not row:
        return {"value": 50, "classification": "Neutral"}
    return {"value": row.value, "classification": row.classification}


def _long_short_data(db: Session, symbols: list[str]) -> list[dict]:
    results = []
    for sym in symbols:
        row = (
            db.query(LongShortRatio)
            .filter(LongShortRatio.symbol == sym.upper())
            .order_by(desc(LongShortRatio.timestamp))
            .first()
        )
        if row:
            results.append(
                {
                    "symbol": row.symbol,
                    "long_ratio": row.long_ratio,
                    "short_ratio": row.short_ratio,
                    "open_interest": row.open_interest,
                }
            )
    return results


def _recent_liquidations(db: Session, hours: int = 24) -> list[dict]:
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        db.query(Liquidation)
        .filter(Liquidation.timestamp >= since)
        .order_by(desc(Liquidation.size))
        .limit(20)
        .all()
    )
    return [
        {
            "symbol": r.symbol,
            "side": r.side,
            "size": r.size,
            "price": r.price,
        }
        for r in rows
    ]


def build_market_context(db: Session) -> dict:
    """Assemble full market context for Claude and signal analysis."""
    watch = settings.watch_coin_list
    prices = _latest_prices(db, limit=20)
    dominance = _latest_dominance(db)
    fear_greed = _latest_fear_greed(db)
    long_short = _long_short_data(db, watch)
    liquidations = _recent_liquidations(db)

    technical_signals = []
    for coin in watch:
        try:
            technical_signals.append(analyse_symbol(db, coin))
        except Exception as e:
            logger.warning("Signal analysis failed for %s: %s", coin, e)

    # Recent lessons from closed trades (learning loop)
    memories = (
        db.query(AgentMemory)
        .order_by(desc(AgentMemory.created_at))
        .limit(10)
        .all()
    )
    past_lessons = [
        {"coin": m.coin, "outcome": m.outcome, "pnl": m.pnl, "lesson": m.lesson}
        for m in memories
    ]

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "prices": prices,
        "dominance": dominance,
        "fear_greed": fear_greed,
        "long_short_ratios": long_short,
        "liquidations": liquidations,
        "technical_signals": technical_signals,
        "watch_coins": watch,
        "past_lessons": past_lessons,
    }


def backtest_setup(db: Session, symbol: str, direction: str, days: int = 30) -> dict:
    """Simple backtest: check if similar RSI/MACD setups were profitable."""
    from agent.signals import _prices_to_dataframe, compute_rsi, compute_macd

    df = _prices_to_dataframe(db, symbol, days=days)
    if df.empty or len(df) < 30:
        return {"valid": False, "win_rate": 0, "sample_size": 0}

    wins = 0
    total = 0
    for i in range(14, len(df) - 5):
        window = df.iloc[: i + 1]
        rsi = compute_rsi(window)
        macd = compute_macd(window)
        if rsi is None:
            continue

        signal = None
        if direction == "long" and rsi < 35 and macd["trend"] == "bullish":
            signal = "long"
        elif direction == "short" and rsi > 65 and macd["trend"] == "bearish":
            signal = "short"

        if signal:
            entry = window["close"].iloc[-1]
            exit_price = df["close"].iloc[i + 5]
            pnl = (exit_price - entry) / entry if signal == "long" else (entry - exit_price) / entry
            wins += 1 if pnl > 0 else 0
            total += 1

    win_rate = (wins / total * 100) if total > 0 else 0
    return {
        "valid": total >= 3,
        "win_rate": round(win_rate, 1),
        "sample_size": total,
        "symbol": symbol,
        "direction": direction,
    }
