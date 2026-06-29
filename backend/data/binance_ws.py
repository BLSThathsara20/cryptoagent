"""Binance WebSocket handler for order book and live trades."""

import asyncio
import json
import logging
import time
from datetime import datetime

import websockets
from sqlalchemy.orm import Session

from config import settings
from db.models import OrderBookEntry, LiveTrade
from db.session import SessionLocal

logger = logging.getLogger(__name__)

# Map coin symbols to Binance trading pairs
SYMBOL_MAP = {
    "BTC": "btcusdt",
    "ETH": "ethusdt",
    "SOL": "solusdt",
    "BNB": "bnbusdt",
    "XRP": "xrpusdt",
    "ADA": "adausdt",
    "DOGE": "dogeusdt",
    "AVAX": "avaxusdt",
    "DOT": "dotusdt",
    "LINK": "linkusdt",
}

_ws_running = False
_last_ws_message_at: datetime | None = None
_ws_message_count = 0
_last_orderbook_store: dict[str, float] = {}  # symbol -> unix timestamp
_last_trade_store: dict[str, float] = {}


def get_ws_status() -> dict:
    return {
        "status": "connected" if _ws_running else "disconnected",
        "last_message_at": _last_ws_message_at.isoformat() if _last_ws_message_at else None,
        "messages_received": _ws_message_count,
    }


def _get_streams() -> list[str]:
    """Build combined stream list for watch coins."""
    coins = settings.watch_coin_list[:5]
    streams = []
    for coin in coins:
        pair = SYMBOL_MAP.get(coin, f"{coin.lower()}usdt")
        streams.append(f"{pair}@depth20@100ms")
        streams.append(f"{pair}@trade")
    return streams


def _store_order_book(db: Session, symbol: str, bids: list, asks: list):
    """Store order book snapshot."""
    coin = symbol.replace("USDT", "").upper()
    for price, qty in bids[:20]:
        db.add(
            OrderBookEntry(
                symbol=coin,
                side="bid",
                price=float(price),
                quantity=float(qty),
            )
        )
    for price, qty in asks[:20]:
        db.add(
            OrderBookEntry(
                symbol=coin,
                side="ask",
                price=float(price),
                quantity=float(qty),
            )
        )


def _store_trade(db: Session, symbol: str, trade: dict):
    """Store a single live trade."""
    coin = symbol.replace("USDT", "").upper()
    db.add(
        LiveTrade(
            symbol=coin,
            side="buy" if trade.get("m") is False else "sell",
            price=float(trade.get("p", 0)),
            quantity=float(trade.get("q", 0)),
        )
    )


async def _handle_message(data: dict):
    """Process incoming WebSocket message with write throttling."""
    global _last_ws_message_at, _ws_message_count
    now = time.time()

    if "b" in data and "a" in data:
        symbol = data.get("s", "BTCUSDT")
        interval = settings.orderbook_store_interval_sec
        if now - _last_orderbook_store.get(symbol, 0) < interval:
            _ws_message_count += 1
            _last_ws_message_at = datetime.utcnow()
            return
        _last_orderbook_store[symbol] = now
    elif "p" in data and "q" in data and data.get("e") == "trade":
        symbol = data.get("s", "BTCUSDT")
        interval = settings.trade_store_interval_sec
        if now - _last_trade_store.get(symbol, 0) < interval:
            _ws_message_count += 1
            _last_ws_message_at = datetime.utcnow()
            return
        _last_trade_store[symbol] = now
    else:
        return

    db = SessionLocal()
    try:
        if "b" in data and "a" in data:
            symbol = data.get("s", "BTCUSDT")
            _store_order_book(db, symbol, data["b"], data["a"])
            db.commit()
            _last_ws_message_at = datetime.utcnow()
            _ws_message_count += 1
        elif "p" in data and "q" in data and data.get("e") == "trade":
            symbol = data.get("s", "BTCUSDT")
            _store_trade(db, symbol, data)
            db.commit()
            _last_ws_message_at = datetime.utcnow()
            _ws_message_count += 1
    except Exception as e:
        logger.error("WS message handling error: %s", e)
        db.rollback()
    finally:
        db.close()


async def binance_ws_loop():
    """Main WebSocket loop with auto-reconnect."""
    global _ws_running
    _ws_running = True

    while _ws_running:
        streams = _get_streams()
        if not streams:
            await asyncio.sleep(10)
            continue

        url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"
        try:
            async with websockets.connect(url, ping_interval=20) as ws:
                logger.info("Binance WebSocket connected (%d streams)", len(streams))
                async for message in ws:
                    if not _ws_running:
                        break
                    payload = json.loads(message)
                    stream_data = payload.get("data", payload)
                    await _handle_message(stream_data)
        except Exception as e:
            logger.error("Binance WS disconnected: %s — reconnecting in 5s", e)
            await asyncio.sleep(5)


def stop_binance_ws():
    """Stop the WebSocket loop."""
    global _ws_running
    _ws_running = False
