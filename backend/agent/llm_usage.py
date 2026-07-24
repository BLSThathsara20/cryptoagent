"""LLM usage tracking, cost estimation, and monthly budget enforcement."""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import desc

from config import settings
from db.models import LLMUsageLog, LLMMonthlySpend

logger = logging.getLogger(__name__)

# USD per 1M tokens (input, output)
MODEL_PRICING = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
}

_last_api_status = {"openai": "unknown", "last_check": None, "last_error": None}
MAX_MONTHLY_HISTORY = 4


def _current_year_month() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost from token counts."""
    key = model.lower()
    for name, (in_price, out_price) in MODEL_PRICING.items():
        if name in key or key in name:
            cost = (input_tokens / 1_000_000 * in_price) + (output_tokens / 1_000_000 * out_price)
            return round(cost, 6)
    # Default to gpt-4o-mini pricing
    cost = (input_tokens / 1_000_000 * 0.15) + (output_tokens / 1_000_000 * 0.60)
    return round(cost, 6)


def _get_or_create_monthly(db: Session, year_month: str, provider: str) -> LLMMonthlySpend:
    row = db.query(LLMMonthlySpend).filter(LLMMonthlySpend.year_month == year_month).first()
    if not row:
        row = LLMMonthlySpend(year_month=year_month, provider=provider)
        db.add(row)
        db.flush()
    return row


def _prune_old_months(db: Session):
    """Keep only the last 4 months of spend history."""
    rows = db.query(LLMMonthlySpend).order_by(desc(LLMMonthlySpend.year_month)).all()
    if len(rows) > MAX_MONTHLY_HISTORY:
        for row in rows[MAX_MONTHLY_HISTORY:]:
            db.delete(row)


def record_llm_usage(
    db: Session,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    success: bool = True,
    error_message: str | None = None,
):
    """Log a single LLM call and update monthly aggregate."""
    total = input_tokens + output_tokens
    cost = estimate_cost(model, input_tokens, output_tokens) if success else 0.0

    db.add(
        LLMUsageLog(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total,
            cost_usd=cost,
            success=success,
            error_message=error_message,
        )
    )

    if success:
        ym = _current_year_month()
        monthly = _get_or_create_monthly(db, ym, provider)
        monthly.total_calls += 1
        monthly.total_tokens += total
        monthly.total_input_tokens += input_tokens
        monthly.total_output_tokens += output_tokens
        monthly.total_cost_usd = round(monthly.total_cost_usd + cost, 6)
        monthly.provider = provider

        # Budget alerts at 80% and 100%
        budget = settings.llm_monthly_budget_usd
        if budget > 0:
            pct = monthly.total_cost_usd / budget * 100
            if pct >= 100 and monthly.total_cost_usd - cost < budget:
                from alerts.manager import create_alert
                create_alert(
                    db, "warning", "system", "AI Budget Reached",
                    f"Monthly OpenAI spend ${monthly.total_cost_usd:.4f} hit ${budget} cap. Using rule-based signals until next month.",
                    commit=False,
                )
            elif pct >= 80 and (monthly.total_cost_usd - cost) / budget * 100 < 80:
                from alerts.manager import create_alert
                create_alert(
                    db, "info", "system", "AI Budget 80%",
                    f"OpenAI spend at {pct:.0f}% of ${budget} monthly budget.",
                    commit=False,
                )

    _prune_old_months(db)
    db.commit()

    if provider == "openai":
        _last_api_status["openai"] = "connected" if success else "error"
        _last_api_status["last_check"] = datetime.utcnow().isoformat()
        if error_message:
            _last_api_status["last_error"] = error_message


def get_current_month_spend(db: Session) -> float:
    row = db.query(LLMMonthlySpend).filter(LLMMonthlySpend.year_month == _current_year_month()).first()
    return round(row.total_cost_usd, 4) if row else 0.0


def is_budget_exceeded(db: Session) -> bool:
    return get_current_month_spend(db) >= settings.llm_monthly_budget_usd


def test_openai_connection() -> dict:
    """Verify OpenAI API key works."""
    if not settings.openai_api_key:
        return {"status": "not_configured", "message": "OPENAI_API_KEY not set"}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        models = client.models.list()
        _last_api_status["openai"] = "connected"
        _last_api_status["last_check"] = datetime.utcnow().isoformat()
        _last_api_status["last_error"] = None
        return {"status": "connected", "message": "OpenAI API is working", "models_available": len(list(models.data)) if models.data else 0}
    except Exception as e:
        _last_api_status["openai"] = "error"
        _last_api_status["last_check"] = datetime.utcnow().isoformat()
        _last_api_status["last_error"] = str(e)
        return {"status": "error", "message": str(e)}


def get_usage_summary(db: Session) -> dict:
    """Full usage stats for dashboard."""
    ym = _current_year_month()
    current = db.query(LLMMonthlySpend).filter(LLMMonthlySpend.year_month == ym).first()
    history = (
        db.query(LLMMonthlySpend)
        .order_by(desc(LLMMonthlySpend.year_month))
        .limit(MAX_MONTHLY_HISTORY)
        .all()
    )
    history = list(reversed(history))

    # Recent calls this month
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    recent_calls = (
        db.query(LLMUsageLog)
        .filter(LLMUsageLog.created_at >= month_start)
        .order_by(desc(LLMUsageLog.created_at))
        .limit(5)
        .all()
    )

    spent = round(current.total_cost_usd, 4) if current else 0.0
    budget = settings.llm_monthly_budget_usd
    tokens = current.total_tokens if current else 0
    calls = current.total_calls if current else 0

    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            api_status, api_message = "not_configured", "OPENAI_API_KEY not set"
        else:
            api_status = _last_api_status.get("openai", "unknown")
            api_message = _last_api_status.get("last_error") or (
                "OpenAI API is working" if api_status == "connected" else ""
            )
    else:
        api_status = _last_api_status.get("openai", "unknown")
        api_message = _last_api_status.get("last_error") or ""

    return {
        "provider": settings.llm_provider,
        "model": settings.openai_model if settings.llm_provider == "openai" else settings.claude_model,
        "api_status": api_status,
        "api_message": api_message,
        "last_api_check": _last_api_status.get("last_check"),
        "current_month": ym,
        "spent_usd": spent,
        "budget_usd": budget,
        "budget_used_percent": round(min(spent / budget * 100, 100), 1) if budget > 0 else 0,
        "budget_remaining_usd": round(max(budget - spent, 0), 4),
        "budget_exceeded": spent >= budget,
        "tokens_this_month": tokens,
        "calls_this_month": calls,
        "input_tokens_this_month": current.total_input_tokens if current else 0,
        "output_tokens_this_month": current.total_output_tokens if current else 0,
        "monthly_history": [
            {
                "month": h.year_month,
                "spent_usd": round(h.total_cost_usd, 4),
                "tokens": h.total_tokens,
                "calls": h.total_calls,
            }
            for h in history
        ],
        "recent_calls": [
            {
                "model": c.model,
                "tokens": c.total_tokens,
                "cost_usd": c.cost_usd,
                "success": c.success,
                "time": c.created_at.isoformat() if c.created_at else None,
            }
            for c in recent_calls
        ],
    }
