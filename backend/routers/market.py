"""Market data API endpoints for the dashboard."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from db.session import get_db
from db.models import (
    CoinPrice,
    MarketDominance,
    OrderBookEntry,
    LiveTrade,
    Liquidation,
    LongShortRatio,
    FearGreedIndex,
)

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/prices")
def get_prices(
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Latest prices for top coins."""
    since = datetime.utcnow() - timedelta(hours=2)
    rows = (
        db.query(CoinPrice)
        .filter(CoinPrice.timestamp >= since)
        .order_by(desc(CoinPrice.timestamp))
        .all()
    )
    seen = set()
    results = []
    for r in rows:
        if r.symbol not in seen:
            seen.add(r.symbol)
            results.append(
                {
                    "symbol": r.symbol,
                    "name": r.name,
                    "price": r.price,
                    "change_24h": r.change_24h,
                    "volume_24h": r.volume_24h,
                    "market_cap": r.market_cap,
                    "rank": r.rank,
                }
            )
        if len(results) >= limit:
            break
    results.sort(key=lambda x: x.get("rank") or 999)
    return results


@router.get("/dominance")
def get_dominance(db: Session = Depends(get_db)):
    """Latest BTC/ETH dominance."""
    row = db.query(MarketDominance).order_by(desc(MarketDominance.timestamp)).first()
    if not row:
        return {"btc_dominance": 0, "eth_dominance": 0, "total_market_cap": 0}
    return {
        "btc_dominance": row.btc_dominance,
        "eth_dominance": row.eth_dominance,
        "total_market_cap": row.total_market_cap,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
    }


@router.get("/fear-greed")
def get_fear_greed(db: Session = Depends(get_db)):
    """Latest Fear & Greed Index."""
    row = db.query(FearGreedIndex).order_by(desc(FearGreedIndex.timestamp)).first()
    if not row:
        return {"value": 50, "classification": "Neutral"}
    return {
        "value": row.value,
        "classification": row.classification,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
    }


@router.get("/orderbook/{symbol}")
def get_orderbook(symbol: str, db: Session = Depends(get_db)):
    """Latest order book for a symbol."""
    latest_ts = (
        db.query(func.max(OrderBookEntry.timestamp))
        .filter(OrderBookEntry.symbol == symbol.upper())
        .scalar()
    )
    if not latest_ts:
        return {"bids": [], "asks": []}

    entries = (
        db.query(OrderBookEntry)
        .filter(
            OrderBookEntry.symbol == symbol.upper(),
            OrderBookEntry.timestamp == latest_ts,
        )
        .all()
    )
    bids = [{"price": e.price, "quantity": e.quantity} for e in entries if e.side == "bid"]
    asks = [{"price": e.price, "quantity": e.quantity} for e in entries if e.side == "ask"]
    bids.sort(key=lambda x: x["price"], reverse=True)
    asks.sort(key=lambda x: x["price"])
    return {"bids": bids, "asks": asks, "symbol": symbol.upper()}


@router.get("/trades/{symbol}")
def get_trades(
    symbol: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Recent live trades for a symbol."""
    rows = (
        db.query(LiveTrade)
        .filter(LiveTrade.symbol == symbol.upper())
        .order_by(desc(LiveTrade.timestamp))
        .limit(limit)
        .all()
    )
    return [
        {
            "symbol": r.symbol,
            "side": r.side,
            "price": r.price,
            "quantity": r.quantity,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in rows
    ]


@router.get("/liquidations")
def get_liquidations(
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Recent liquidations across all coins."""
    since = datetime.utcnow() - timedelta(hours=24)
    rows = (
        db.query(Liquidation)
        .filter(Liquidation.timestamp >= since)
        .order_by(desc(Liquidation.size))
        .limit(limit)
        .all()
    )
    return [
        {
            "symbol": r.symbol,
            "side": r.side,
            "size": r.size,
            "price": r.price,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in rows
    ]


@router.get("/long-short")
def get_long_short(db: Session = Depends(get_db)):
    """Latest long/short ratios per coin."""
    since = datetime.utcnow() - timedelta(hours=6)
    symbols = (
        db.query(LongShortRatio.symbol)
        .filter(LongShortRatio.timestamp >= since)
        .distinct()
        .all()
    )
    results = []
    for (sym,) in symbols:
        row = (
            db.query(LongShortRatio)
            .filter(LongShortRatio.symbol == sym, LongShortRatio.timestamp >= since)
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


@router.get("/candles/{symbol}")
def get_candles(
    symbol: str,
    limit: int = Query(100, ge=10, le=500),
    db: Session = Depends(get_db),
):
    """Price history for candlestick chart."""
    since = datetime.utcnow() - timedelta(days=7)
    rows = (
        db.query(CoinPrice)
        .filter(CoinPrice.symbol == symbol.upper(), CoinPrice.timestamp >= since)
        .order_by(CoinPrice.timestamp)
        .all()
    )
    # Downsample if too many points
    step = max(1, len(rows) // limit)
    sampled = rows[::step][-limit:]
    return [
        {
            "time": int(r.timestamp.timestamp()) if r.timestamp else 0,
            "open": r.price,
            "high": r.price * 1.001,
            "low": r.price * 0.999,
            "close": r.price,
            "volume": r.volume_24h or 0,
        }
        for r in sampled
    ]
