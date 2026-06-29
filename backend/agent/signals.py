"""Technical signal analysis (RSI, MACD, volume spikes) using pandas/numpy."""

import logging
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import desc

from db.models import CoinPrice, LiveTrade

logger = logging.getLogger(__name__)


def _prices_to_dataframe(db: Session, symbol: str, days: int = 30) -> pd.DataFrame:
    """Build OHLCV-like dataframe from stored price snapshots."""
    since = datetime.utcnow() - timedelta(days=days)
    prices = (
        db.query(CoinPrice)
        .filter(CoinPrice.symbol == symbol.upper(), CoinPrice.timestamp >= since)
        .order_by(CoinPrice.timestamp)
        .all()
    )
    if len(prices) < 14:
        return pd.DataFrame()

    df = pd.DataFrame(
        {
            "timestamp": [p.timestamp for p in prices],
            "close": [p.price for p in prices],
            "volume": [p.volume_24h or 0 for p in prices],
        }
    )
    df.set_index("timestamp", inplace=True)
    return df


def compute_rsi(df: pd.DataFrame, period: int = 14) -> float | None:
    """Calculate latest RSI value using Wilder's smoothing."""
    if df.empty or len(df) < period + 1:
        return None
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return float(val) if not pd.isna(val) else None


def compute_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """Calculate MACD signal."""
    if df.empty or len(df) < slow + signal:
        return {"macd": None, "signal": None, "histogram": None, "trend": "neutral"}

    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    macd_val = float(macd_line.iloc[-1]) if not pd.isna(macd_line.iloc[-1]) else None
    signal_val = float(signal_line.iloc[-1]) if not pd.isna(signal_line.iloc[-1]) else None
    hist_val = float(histogram.iloc[-1]) if not pd.isna(histogram.iloc[-1]) else None

    trend = "bullish" if hist_val and hist_val > 0 else "bearish" if hist_val and hist_val < 0 else "neutral"
    return {"macd": macd_val, "signal": signal_val, "histogram": hist_val, "trend": trend}


def detect_volume_spike(df: pd.DataFrame, threshold: float = 2.0) -> dict:
    """Detect if current volume is significantly above average."""
    if df.empty or len(df) < 10:
        return {"spike": False, "ratio": 1.0}

    avg_vol = df["volume"].rolling(20).mean().iloc[-1]
    current_vol = df["volume"].iloc[-1]
    if avg_vol and avg_vol > 0:
        ratio = current_vol / avg_vol
        return {"spike": ratio >= threshold, "ratio": round(ratio, 2)}
    return {"spike": False, "ratio": 1.0}


def get_order_book_imbalance(db: Session, symbol: str) -> dict:
    """Calculate bid/ask imbalance from latest order book."""
    from db.models import OrderBookEntry

    latest = (
        db.query(OrderBookEntry.timestamp)
        .filter(OrderBookEntry.symbol == symbol.upper())
        .order_by(desc(OrderBookEntry.timestamp))
        .first()
    )
    if not latest:
        return {"bid_volume": 0, "ask_volume": 0, "imbalance": 0}

    entries = (
        db.query(OrderBookEntry)
        .filter(
            OrderBookEntry.symbol == symbol.upper(),
            OrderBookEntry.timestamp == latest[0],
        )
        .all()
    )
    bid_vol = sum(e.quantity for e in entries if e.side == "bid")
    ask_vol = sum(e.quantity for e in entries if e.side == "ask")
    total = bid_vol + ask_vol
    imbalance = (bid_vol - ask_vol) / total if total > 0 else 0
    return {
        "bid_volume": round(bid_vol, 4),
        "ask_volume": round(ask_vol, 4),
        "imbalance": round(imbalance, 4),
    }


def analyse_symbol(db: Session, symbol: str) -> dict:
    """Run all technical signals for a symbol."""
    df = _prices_to_dataframe(db, symbol)
    rsi = compute_rsi(df)
    macd = compute_macd(df)
    volume = detect_volume_spike(df)
    ob = get_order_book_imbalance(db, symbol)

    # Composite signal score (-100 to +100)
    score = 0
    if rsi:
        if rsi < 30:
            score += 30  # oversold — bullish
        elif rsi > 70:
            score -= 30  # overbought — bearish

    if macd["trend"] == "bullish":
        score += 25
    elif macd["trend"] == "bearish":
        score -= 25

    if volume["spike"]:
        score += 15 if score >= 0 else -15

    if ob["imbalance"] > 0.1:
        score += 10
    elif ob["imbalance"] < -0.1:
        score -= 10

    return {
        "symbol": symbol.upper(),
        "rsi": rsi,
        "macd": macd,
        "volume": volume,
        "order_book": ob,
        "signal_score": max(-100, min(100, score)),
    }
