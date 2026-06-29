"""SQLAlchemy models for all market data, trades, and agent decisions."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.sql import func

from db.session import Base


class CoinPrice(Base):
    __tablename__ = "coin_prices"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), index=True, nullable=False)
    name = Column(String(100))
    price = Column(Float, nullable=False)
    volume_24h = Column(Float)
    change_24h = Column(Float)
    market_cap = Column(Float)
    rank = Column(Integer)
    timestamp = Column(DateTime, default=func.now(), index=True)


class MarketDominance(Base):
    __tablename__ = "market_dominance"

    id = Column(Integer, primary_key=True, index=True)
    btc_dominance = Column(Float)
    eth_dominance = Column(Float)
    total_market_cap = Column(Float)
    timestamp = Column(DateTime, default=func.now(), index=True)


class OrderBookEntry(Base):
    __tablename__ = "order_book"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), index=True, nullable=False)
    side = Column(String(4), nullable=False)  # bid or ask
    price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=func.now(), index=True)


class LiveTrade(Base):
    __tablename__ = "live_trades"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), index=True, nullable=False)
    side = Column(String(4), nullable=False)  # buy or sell
    price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=func.now(), index=True)


class Liquidation(Base):
    __tablename__ = "liquidations"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), index=True, nullable=False)
    side = Column(String(10), nullable=False)  # long or short
    size = Column(Float, nullable=False)
    price = Column(Float)
    timestamp = Column(DateTime, default=func.now(), index=True)


class LongShortRatio(Base):
    __tablename__ = "long_short_ratios"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), index=True, nullable=False)
    long_ratio = Column(Float)
    short_ratio = Column(Float)
    open_interest = Column(Float)
    timestamp = Column(DateTime, default=func.now(), index=True)


class FearGreedIndex(Base):
    __tablename__ = "fear_greed_index"

    id = Column(Integer, primary_key=True, index=True)
    value = Column(Integer, nullable=False)
    classification = Column(String(50))
    timestamp = Column(DateTime, default=func.now(), index=True)


class AgentDecision(Base):
    __tablename__ = "agent_decisions"

    id = Column(Integer, primary_key=True, index=True)
    coin = Column(String(20), nullable=False)
    direction = Column(String(10), nullable=False)  # long or short
    entry_price = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    reasoning = Column(Text)
    technical_signals = Column(JSON)
    status = Column(String(20), default="pending")  # pending, win, loss, cancelled
    outcome_pnl = Column(Float)
    created_at = Column(DateTime, default=func.now(), index=True)
    closed_at = Column(DateTime)


class PaperAccount(Base):
    __tablename__ = "paper_account"

    id = Column(Integer, primary_key=True, index=True)
    balance = Column(Float, nullable=False)
    initial_balance = Column(Float, nullable=False)
    total_pnl = Column(Float, default=0.0)
    win_count = Column(Integer, default=0)
    loss_count = Column(Integer, default=0)
    max_drawdown = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class PaperPnLHistory(Base):
    __tablename__ = "paper_pnl_history"

    id = Column(Integer, primary_key=True, index=True)
    balance = Column(Float, nullable=False)
    pnl = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=func.now(), index=True)


class AgentStatus(Base):
    __tablename__ = "agent_status"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(20), default="idle")  # idle, running, analysing
    live_mode = Column(Boolean, default=False)
    loop_interval = Column(Integer, default=300)
    max_risk_percent = Column(Float, default=2.0)
    watch_coins = Column(String(500))
    last_run_at = Column(DateTime)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class AgentMemory(Base):
    """Lessons learned from closed trades — fed back into agent context."""

    __tablename__ = "agent_memories"

    id = Column(Integer, primary_key=True, index=True)
    coin = Column(String(20), nullable=False)
    direction = Column(String(10))
    outcome = Column(String(10), nullable=False)  # win or loss
    pnl = Column(Float)
    lesson = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now(), index=True)


class PortfolioSnapshot(Base):
    """Point-in-time snapshot of fund allocation."""

    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(20), default="paper")  # paper or binance
    total_usd = Column(Float, nullable=False)
    stable_usd = Column(Float, default=0)
    crypto_usd = Column(Float, default=0)
    deployed_usd = Column(Float, default=0)
    available_usd = Column(Float, default=0)
    holdings = Column(JSON)  # [{asset, amount, usd_value, percent}]
    created_at = Column(DateTime, default=func.now(), index=True)


class FundManagerDecision(Base):
    """Fund manager agent decisions and recommendations."""

    __tablename__ = "fund_manager_decisions"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(30), nullable=False)  # hold, deploy, reduce, rebalance, reserve
    asset = Column(String(20))
    amount_usd = Column(Float)
    reasoning = Column(Text, nullable=False)
    portfolio_total = Column(Float)
    target_daily_profit = Column(Float)
    status = Column(String(20), default="recommended")  # recommended, executed, skipped
    created_at = Column(DateTime, default=func.now(), index=True)


class SystemAlert(Base):
    """System alerts for trades, connectivity, and agent events."""

    __tablename__ = "system_alerts"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(10), nullable=False)  # info, success, warning, error
    category = Column(String(20), nullable=False)  # system, trading, fund_manager, binance, data
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now(), index=True)
