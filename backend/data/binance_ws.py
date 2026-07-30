"""Binance WebSocket handler for order book and live trades.

Auto-reconnects after offline/hotspot drops. Uses keepalive + stale-message
watchdog so half-open sockets do not hang forever without reconnecting.
"""

from __future__ import annotations

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

# Force reconnect if no message for this long (seconds)
WS_STALE_FORCE_SEC = 60
WS_RECV_TIMEOUT_SEC = 25
WS_BACKOFF_START = 3
WS_BACKOFF_MAX = 60

_ws_running = False
_ws_socket_connected = False
_last_ws_message_at: datetime | None = None
_ws_message_count = 0
_last_orderbook_store: dict[str, float] = {}
_last_trade_store: dict[str, float] = {}
_msg_queue: asyncio.Queue | None = None
_consumer_task: asyncio.Task | None = None
_ws_task: asyncio.Task | None = None
_reconnect_backoff = WS_BACKOFF_START


def get_ws_status() -> dict:
    stale = True
    age = None
    if _last_ws_message_at:
        age = (datetime.utcnow() - _last_ws_message_at).total_seconds()
        stale = age > 45
    connected = _ws_socket_connected and not stale
    task_alive = _ws_task is not None and not _ws_task.done()
    return {
        "status": "connected" if connected else "disconnected",
        "socket_connected": _ws_socket_connected,
        "task_alive": task_alive,
        "last_message_at": _last_ws_message_at.isoformat() if _last_ws_message_at else None,
        "message_age_sec": round(age, 1) if age is not None else None,
        "messages_received": _ws_message_count,
    }


def _touch_ws_liveness():
    global _last_ws_message_at, _ws_message_count, _reconnect_backoff
    _last_ws_message_at = datetime.utcnow()
    _ws_message_count += 1
    _reconnect_backoff = WS_BACKOFF_START


def _get_streams() -> list[str]:
    """Combined streams — 1000ms depth (not 100ms) to cut load ~10x."""
    coins = settings.watch_coin_list[:5]
    streams = []
    for coin in coins:
        pair = SYMBOL_MAP.get(coin, f"{coin.lower()}usdt")
        streams.append(f"{pair}@depth20@1000ms")
        streams.append(f"{pair}@trade")
    return streams


def _store_order_book(db: Session, symbol: str, bids: list, asks: list):
    coin = symbol.replace("USDT", "").upper()
    for price, qty in bids[:10]:
        db.add(
            OrderBookEntry(
                symbol=coin,
                side="bid",
                price=float(price),
                quantity=float(qty),
            )
        )
    for price, qty in asks[:10]:
        db.add(
            OrderBookEntry(
                symbol=coin,
                side="ask",
                price=float(price),
                quantity=float(qty),
            )
        )


def _store_trade(db: Session, symbol: str, trade: dict):
    coin = symbol.replace("USDT", "").upper()
    db.add(
        LiveTrade(
            symbol=coin,
            side="buy" if trade.get("m") is False else "sell",
            price=float(trade.get("p", 0)),
            quantity=float(trade.get("q", 0)),
        )
    )


def _persist_message(data: dict) -> bool:
    """Sync DB write — always run in a worker thread."""
    global _last_ws_message_at, _ws_message_count
    now = time.time()

    if "b" in data and "a" in data:
        symbol = data.get("s", "BTCUSDT")
        interval = max(3.0, float(settings.orderbook_store_interval_sec))
        if now - _last_orderbook_store.get(symbol, 0) < interval:
            _ws_message_count += 1
            _last_ws_message_at = datetime.utcnow()
            return False
        _last_orderbook_store[symbol] = now
        kind = "book"
    elif "p" in data and "q" in data and data.get("e") == "trade":
        symbol = data.get("s", "BTCUSDT")
        interval = max(1.0, float(settings.trade_store_interval_sec))
        if now - _last_trade_store.get(symbol, 0) < interval:
            _ws_message_count += 1
            _last_ws_message_at = datetime.utcnow()
            return False
        _last_trade_store[symbol] = now
        kind = "trade"
    else:
        return False

    db = SessionLocal()
    try:
        if kind == "book":
            _store_order_book(db, symbol, data["b"], data["a"])
        else:
            _store_trade(db, symbol, data)
        db.commit()
        _last_ws_message_at = datetime.utcnow()
        _ws_message_count += 1
        return True
    except Exception as e:
        logger.error("WS message handling error: %s", e)
        db.rollback()
        return False
    finally:
        db.close()


async def _queue_consumer():
    """Drain WS queue without blocking the receive/pong loop."""
    global _msg_queue
    while _ws_running:
        if _msg_queue is None:
            await asyncio.sleep(0.2)
            continue
        try:
            data = await asyncio.wait_for(_msg_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        try:
            await asyncio.to_thread(_persist_message, data)
        except Exception as e:
            logger.error("WS consumer error: %s", e)
        finally:
            _msg_queue.task_done()


def _message_age_sec() -> float | None:
    if not _last_ws_message_at:
        return None
    return (datetime.utcnow() - _last_ws_message_at).total_seconds()


async def binance_ws_loop():
    """Main WebSocket loop with auto-reconnect and non-blocking persistence."""
    global _ws_running, _ws_socket_connected, _msg_queue, _consumer_task, _reconnect_backoff
    _ws_running = True
    if _msg_queue is None:
        _msg_queue = asyncio.Queue(maxsize=200)
    if _consumer_task is None or _consumer_task.done():
        _consumer_task = asyncio.create_task(_queue_consumer())

    while _ws_running:
        streams = _get_streams()
        if not streams:
            await asyncio.sleep(10)
            continue

        url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"
        try:
            # Keepalive so dead/hotspot half-open sockets fail fast and reconnect
            async with websockets.connect(
                url,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
                max_queue=64,
                open_timeout=20,
            ) as ws:
                _ws_socket_connected = True
                _reconnect_backoff = WS_BACKOFF_START
                logger.info("Binance WebSocket connected (%d streams)", len(streams))
                while _ws_running:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=WS_RECV_TIMEOUT_SEC)
                    except asyncio.TimeoutError:
                        age = _message_age_sec()
                        if age is None or age > WS_STALE_FORCE_SEC:
                            raise TimeoutError(
                                f"No WS messages for {age or 'ever'}s — forcing reconnect"
                            )
                        # Still within grace: send ping manually if needed
                        try:
                            pong = await ws.ping()
                            await asyncio.wait_for(pong, timeout=10)
                        except Exception as ping_err:
                            raise TimeoutError(f"WS ping failed: {ping_err}") from ping_err
                        continue

                    _touch_ws_liveness()
                    try:
                        payload = json.loads(message)
                        stream_data = payload.get("data", payload)
                        assert _msg_queue is not None
                        _msg_queue.put_nowait(stream_data)
                    except asyncio.QueueFull:
                        pass
                    except Exception as e:
                        logger.debug("WS parse skip: %s", e)
        except asyncio.CancelledError:
            break
        except Exception as e:
            _ws_socket_connected = False
            delay = _reconnect_backoff
            _reconnect_backoff = min(WS_BACKOFF_MAX, max(WS_BACKOFF_START, delay * 2))
            logger.warning(
                "Binance WS disconnected: %s — reconnecting in %ss",
                e,
                delay,
            )
            await asyncio.sleep(delay)
        finally:
            _ws_socket_connected = False

    if _consumer_task and not _consumer_task.done():
        _consumer_task.cancel()
        try:
            await _consumer_task
        except Exception:
            pass


def start_binance_ws() -> asyncio.Task:
    """Start (or return existing) WebSocket background task."""
    global _ws_task, _ws_running
    if _ws_task is not None and not _ws_task.done():
        return _ws_task
    _ws_running = True
    _ws_task = asyncio.create_task(binance_ws_loop())
    logger.info("Binance WebSocket task started")
    return _ws_task


def ensure_ws_running() -> bool:
    """
    Respawn the WS task if it died. Returns True if a new task was started.
    Safe to call from autopilot after network recovery.
    """
    global _ws_task, _ws_running, _reconnect_backoff
    if _ws_task is not None and not _ws_task.done():
        # Soft nudge: if socket thinks connected but messages are stale, cancel to reconnect
        age = _message_age_sec()
        if _ws_socket_connected and age is not None and age > WS_STALE_FORCE_SEC:
            logger.warning("WS stale (%ss) — cancelling task to force reconnect", int(age))
            _ws_task.cancel()
            _reconnect_backoff = WS_BACKOFF_START
        else:
            return False
    _ws_running = True
    _reconnect_backoff = WS_BACKOFF_START
    _ws_task = asyncio.create_task(binance_ws_loop())
    logger.info("Binance WebSocket task respawned after offline/stale")
    return True


def stop_binance_ws():
    """Stop the WebSocket loop."""
    global _ws_running, _ws_socket_connected, _ws_task
    _ws_running = False
    _ws_socket_connected = False
    if _ws_task and not _ws_task.done():
        _ws_task.cancel()
    _ws_task = None
