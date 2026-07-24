"""SQLAlchemy database session and engine setup."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

from config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,  # recycle connections every hour (long-run stability)
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables and composite indexes on startup."""
    from db import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _ensure_indexes()


def _ensure_indexes():
    """Add composite indexes for time-range queries (idempotent)."""
    indexes = [
        "CREATE INDEX IF NOT EXISTS ix_coin_prices_symbol_ts ON coin_prices (symbol, timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS ix_order_book_symbol_ts ON order_book (symbol, timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS ix_live_trades_symbol_ts ON live_trades (symbol, timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS ix_coin_prices_ts ON coin_prices (timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS ix_order_book_ts ON order_book (timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS ix_live_trades_ts ON live_trades (timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS ix_agent_decisions_created ON agent_decisions (created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_system_alerts_created ON system_alerts (created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_llm_usage_logs_created ON llm_usage_logs (created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_llm_monthly_spend_ym ON llm_monthly_spend (year_month DESC)",
        "CREATE INDEX IF NOT EXISTS ix_system_issues_created ON system_issues (created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_agent_memories_created ON agent_memories (created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_portfolio_snapshots_created ON portfolio_snapshots (created_at DESC)",
    ]
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for sql in indexes:
            try:
                conn.execute(text(sql))
            except Exception:
                pass
