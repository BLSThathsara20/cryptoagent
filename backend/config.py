"""Application configuration from environment variables."""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://cryptoagent:changeme@localhost:5432/cryptoagent",
    )
    claude_api_key: str = os.getenv("CLAUDE_API_KEY", "")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")  # openai or claude
    llm_monthly_budget_usd: float = float(os.getenv("LLM_MONTHLY_BUDGET_USD", "5"))
    binance_api_key: str = os.getenv("BINANCE_API_KEY", "")
    binance_secret: str = os.getenv("BINANCE_SECRET", "")
    coinglass_api_key: str = os.getenv("COINGLASS_API_KEY", "")
    live_mode: bool = os.getenv("LIVE_MODE", "false").lower() == "true"
    starting_balance: float = float(os.getenv("STARTING_BALANCE", "10000"))
    agent_loop_interval: int = int(os.getenv("AGENT_LOOP_INTERVAL", "300"))
    max_risk_percent: float = float(os.getenv("MAX_RISK_PERCENT", "2"))
    watch_coins: str = os.getenv(
        "WATCH_COINS", "BTC,ETH,SOL,BNB,XRP,ADA,DOGE,AVAX,DOT,LINK"
    )
    fund_reserve_percent: float = float(os.getenv("FUND_RESERVE_PERCENT", "30"))
    max_allocation_per_coin: float = float(os.getenv("MAX_ALLOCATION_PER_COIN", "25"))
    daily_profit_target_percent: float = float(os.getenv("DAILY_PROFIT_TARGET_PERCENT", "0.5"))

    # Trading style — short holds, tight levels, limited concurrent risk
    max_open_trades: int = int(os.getenv("MAX_OPEN_TRADES", "2"))
    max_hold_minutes: int = int(os.getenv("MAX_HOLD_MINUTES", "30"))
    trade_sl_percent: float = float(os.getenv("TRADE_SL_PERCENT", "0.8"))
    trade_tp_percent: float = float(os.getenv("TRADE_TP_PERCENT", "1.2"))
    min_confidence_to_trade: float = float(os.getenv("MIN_CONFIDENCE_TO_TRADE", "55"))
    stop_new_trades_when_target_hit: bool = (
        os.getenv("STOP_NEW_TRADES_WHEN_TARGET_HIT", "true").lower() == "true"
    )

    # OpenAI cost control — selective by default (rules first, LLM only when needed)
    llm_mode: str = os.getenv("LLM_MODE", "selective")  # selective | always | rules_only
    llm_cooldown_sec: int = int(os.getenv("LLM_COOLDOWN_SEC", "900"))
    llm_min_signal: float = float(os.getenv("LLM_MIN_SIGNAL", "25"))
    llm_strong_signal: float = float(os.getenv("LLM_STRONG_SIGNAL", "45"))
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "350"))

    # Long-run data retention (days) — prevents DB from growing forever
    retain_orderbook_days: int = int(os.getenv("RETAIN_ORDERBOOK_DAYS", "7"))
    retain_live_trades_days: int = int(os.getenv("RETAIN_LIVE_TRADES_DAYS", "7"))
    retain_coin_prices_days: int = int(os.getenv("RETAIN_COIN_PRICES_DAYS", "90"))
    retain_market_meta_days: int = int(os.getenv("RETAIN_MARKET_META_DAYS", "90"))
    retain_alerts_days: int = int(os.getenv("RETAIN_ALERTS_DAYS", "30"))
    retain_portfolio_snapshots_days: int = int(os.getenv("RETAIN_PORTFOLIO_SNAPSHOTS_DAYS", "30"))
    retain_news_days: int = int(os.getenv("RETAIN_NEWS_DAYS", "14"))
    retain_feature_snapshots: int = int(os.getenv("RETAIN_FEATURE_SNAPSHOTS", "2000"))
    retain_paper_pnl_days: int = int(os.getenv("RETAIN_PAPER_PNL_DAYS", "180"))
    retain_llm_monthly_months: int = int(os.getenv("RETAIN_LLM_MONTHLY_MONTHS", "4"))

    # Regime shift — reduce size / pause when market character or learning drifts
    regime_size_reduction_on_shift: float = float(os.getenv("REGIME_SIZE_REDUCTION_ON_SHIFT", "0.5"))
    regime_min_confidence_boost_on_shift: float = float(os.getenv("REGIME_MIN_CONFIDENCE_BOOST", "10"))
    regime_size_reduction_on_drift: float = float(os.getenv("REGIME_SIZE_REDUCTION_ON_DRIFT", "0.5"))
    regime_confidence_boost_on_drift: float = float(os.getenv("REGIME_CONFIDENCE_BOOST_ON_DRIFT", "5"))
    regime_learning_negative_days: int = int(os.getenv("REGIME_LEARNING_NEGATIVE_DAYS", "2"))
    regime_learning_rate_negative_threshold: float = float(os.getenv("REGIME_LEARNING_RATE_THRESHOLD", "-5"))
    regime_pause_accuracy_drop: float = float(os.getenv("REGIME_PAUSE_ACCURACY_DROP", "15"))
    regime_drawdown_pause_pct: float = float(os.getenv("REGIME_DRAWDOWN_PAUSE_PCT", "20"))
    regime_min_win_rate_pct: float = float(os.getenv("REGIME_MIN_WIN_RATE_PCT", "35"))
    regime_lesson_cap_on_shift: int = int(os.getenv("REGIME_LESSON_CAP_ON_SHIFT", "3"))
    regime_lesson_cap_on_drift: int = int(os.getenv("REGIME_LESSON_CAP_ON_DRIFT", "5"))
    retain_regime_logs_days: int = int(os.getenv("RETAIN_REGIME_LOGS_DAYS", "14"))

    # WebSocket write throttling — reduces DB writes 10-100x
    orderbook_store_interval_sec: int = int(os.getenv("ORDERBOOK_STORE_INTERVAL_SEC", "5"))
    trade_store_interval_sec: float = float(os.getenv("TRADE_STORE_INTERVAL_SEC", "1"))

    # Autopilot — zero-touch operations
    auto_backup_enabled: bool = os.getenv("AUTO_BACKUP_ENABLED", "true").lower() == "true"
    auto_backup_retain_count: int = int(os.getenv("AUTO_BACKUP_RETAIN_COUNT", "14"))
    backup_dir: str = os.getenv("BACKUP_DIR", "/backups")
    auto_recovery_enabled: bool = os.getenv("AUTO_RECOVERY_ENABLED", "true").lower() == "true"
    db_size_warn_mb: float = float(os.getenv("DB_SIZE_WARN_MB", "3000"))

    @property
    def watch_coin_list(self) -> list[str]:
        return [c.strip().upper() for c in self.watch_coins.split(",") if c.strip()]

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "claude":
            return bool(self.claude_api_key)
        return bool(self.openai_api_key)

    @property
    def active_llm_label(self) -> str:
        if self.llm_provider == "claude" and self.claude_api_key:
            return f"Claude ({self.claude_model})"
        if self.openai_api_key:
            return f"OpenAI ({self.openai_model})"
        return "Rule-based (no LLM)"

    class Config:
        env_file = ".env"


settings = Settings()
