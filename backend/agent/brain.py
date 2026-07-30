"""LLM integration — selective OpenAI use, compact prompts, short-hold setups."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

import anthropic
from openai import OpenAI
from sqlalchemy.orm import Session

from config import settings
from agent.analyser import backtest_setup
from agent.llm_usage import record_llm_usage, is_budget_exceeded

logger = logging.getLogger(__name__)

_last_llm_call_at: datetime | None = None
_last_llm_skip_reason: str = "startup"

SYSTEM_PROMPT = """You are a crypto scalp analyst. Prefer SHORT holds (minutes to ~1 hour), not swing trades.

Rules:
- Always include stop_loss
- Risk/reward at least 1:1.4 (TP distance >= 1.4x SL)
- Prefer tight levels: SL about 0.6-1.0%, TP about 1.0-1.6% from entry
- Use fear/greed, news headlines, and past_lessons
- Return ONLY valid JSON

{
  "coin": "BTC",
  "direction": "long" or "short",
  "entry": 95000.0,
  "take_profit": 96140.0,
  "stop_loss": 94240.0,
  "confidence": 75,
  "reasoning": "Short explanation (2-3 sentences max)"
}"""


def get_llm_skip_meta() -> dict:
    return {
        "last_call_at": _last_llm_call_at.isoformat() if _last_llm_call_at else None,
        "last_skip_reason": _last_llm_skip_reason,
        "mode": settings.llm_mode,
        "cooldown_sec": settings.llm_cooldown_sec,
    }


def _best_abs_signal(context: dict) -> float:
    signals = context.get("technical_signals") or []
    if not signals:
        return 0.0
    return max(abs(float(s.get("signal_score") or 0)) for s in signals if isinstance(s, dict))


def _compact_context(context: dict) -> dict:
    """Shrink payload — biggest OpenAI cost saver."""
    prices = []
    for p in (context.get("prices") or [])[:6]:
        if not isinstance(p, dict):
            continue
        prices.append({
            "symbol": p.get("symbol"),
            "price": p.get("price"),
            "change_24h": p.get("change_24h"),
        })

    signals = []
    for s in context.get("technical_signals") or []:
        if not isinstance(s, dict):
            continue
        score = float(s.get("signal_score") or 0)
        if abs(score) < 12:
            continue
        macd = s.get("macd") or {}
        signals.append({
            "symbol": s.get("symbol"),
            "rsi": s.get("rsi"),
            "macd": macd.get("trend") if isinstance(macd, dict) else None,
            "score": round(score, 1),
        })
    signals.sort(key=lambda x: abs(x.get("score") or 0), reverse=True)

    lessons = []
    for m in (context.get("past_lessons") or [])[:3]:
        if not isinstance(m, dict):
            continue
        lessons.append({
            "coin": m.get("coin"),
            "outcome": m.get("outcome"),
            "lesson": str(m.get("lesson") or "")[:140],
        })

    news = []
    for n in (context.get("recent_news") or [])[:3]:
        if isinstance(n, dict) and n.get("title"):
            news.append({"title": str(n["title"])[:120], "source": n.get("source")})

    return {
        "prices": prices,
        "fear_greed": context.get("fear_greed"),
        "signals": signals[:8],
        "past_lessons": lessons,
        "news": news,
        "portfolio": context.get("portfolio"),
        "watch": (context.get("watch_coins") or [])[:8],
        "style": {
            "max_hold_minutes": settings.max_hold_minutes,
            "sl_pct": settings.trade_sl_percent,
            "tp_pct": settings.trade_tp_percent,
        },
    }


def apply_scalp_levels(decision: dict) -> dict:
    """Enforce tight TP/SL for short-hold style."""
    entry = float(decision.get("entry") or 0)
    if entry <= 0:
        return decision
    direction = decision.get("direction")
    sl_pct = max(0.3, float(settings.trade_sl_percent)) / 100.0
    tp_pct = max(sl_pct * 1.4, float(settings.trade_tp_percent) / 100.0)

    if direction == "long":
        decision["stop_loss"] = round(entry * (1 - sl_pct), 6)
        decision["take_profit"] = round(entry * (1 + tp_pct), 6)
    elif direction == "short":
        decision["stop_loss"] = round(entry * (1 + sl_pct), 6)
        decision["take_profit"] = round(entry * (1 - tp_pct), 6)
    return decision


def _build_user_message(context: dict) -> str:
    compact = _compact_context(context)
    return (
        "Pick the best short-hold trade (or none). Compact market data:\n"
        + json.dumps(compact, separators=(",", ":"), default=str)
    )


def _parse_decision(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


def _validate_decision(decision: dict, db: Session) -> dict | None:
    required = ["coin", "direction", "entry", "take_profit", "stop_loss", "confidence", "reasoning"]
    for field in required:
        if field not in decision:
            logger.error("LLM response missing field: %s", field)
            return None
    if not decision.get("stop_loss"):
        logger.error("LLM returned trade without stop_loss — rejected")
        return None
    decision = apply_scalp_levels(decision)
    if float(decision.get("confidence") or 0) < settings.min_confidence_to_trade:
        logger.info(
            "Decision below min confidence (%.1f < %.1f) — rejected",
            float(decision.get("confidence") or 0),
            settings.min_confidence_to_trade,
        )
        return None
    bt = backtest_setup(db, decision["coin"], decision["direction"])
    decision["backtest"] = bt
    decision["reasoning"] = str(decision.get("reasoning") or "")[:400]
    return decision


def _cooldown_active() -> bool:
    if not _last_llm_call_at:
        return False
    age = (datetime.utcnow() - _last_llm_call_at).total_seconds()
    return age < settings.llm_cooldown_sec


def should_use_llm(context: dict) -> tuple[bool, str]:
    """Decide whether this cycle pays for an LLM call."""
    mode = (settings.llm_mode or "selective").lower()
    if mode == "rules_only":
        return False, "rules_only"
    if mode == "always":
        if _cooldown_active():
            return False, "cooldown"
        return True, "always"

    # selective (default)
    if _cooldown_active():
        return False, "cooldown"

    score = _best_abs_signal(context)
    if score < settings.llm_min_signal:
        return False, "weak_signal"
    # Clear technical edge → rules are enough (save OpenAI $)
    if score >= settings.llm_strong_signal:
        return False, "strong_rules"
    # Ambiguous mid-band → spend one cheap LLM call
    return True, "ambiguous"


async def _call_openai(context: dict, db: Session) -> dict | None:
    if is_budget_exceeded(db):
        logger.warning("OpenAI monthly budget exceeded — skipping LLM call")
        return None

    client = OpenAI(api_key=settings.openai_api_key)

    def _request():
        return client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=settings.llm_max_tokens,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_message(context)},
            ],
            response_format={"type": "json_object"},
        )

    try:
        # Sync SDK — offload so FastAPI/UI polls keep working
        response = await asyncio.to_thread(_request)
        usage = response.usage
        record_llm_usage(
            db,
            provider="openai",
            model=settings.openai_model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            success=True,
        )
        text = response.choices[0].message.content or ""
        decision = _parse_decision(text)
        return _validate_decision(decision, db)
    except Exception as e:
        record_llm_usage(
            db, "openai", settings.openai_model, 0, 0, success=False, error_message=str(e)[:500]
        )
        raise


async def _call_claude(context: dict, db: Session) -> dict | None:
    if is_budget_exceeded(db):
        logger.warning("LLM monthly budget exceeded — skipping Claude call")
        return None

    client = anthropic.Anthropic(api_key=settings.claude_api_key)

    def _request():
        return client.messages.create(
            model=settings.claude_model,
            max_tokens=settings.llm_max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_message(context)}],
        )

    try:
        response = await asyncio.to_thread(_request)
        input_t = response.usage.input_tokens if response.usage else 0
        output_t = response.usage.output_tokens if response.usage else 0
        record_llm_usage(
            db, "claude", settings.claude_model, input_t, output_t, success=True
        )
        text = response.content[0].text.strip()
        decision = _parse_decision(text)
        return _validate_decision(decision, db)
    except Exception as e:
        record_llm_usage(
            db, "claude", settings.claude_model, 0, 0, success=False, error_message=str(e)[:500]
        )
        raise


async def get_llm_decision(context: dict, db: Session) -> dict | None:
    """Selective LLM: rules first; OpenAI only when ambiguous and cooldown allows."""
    global _last_llm_call_at, _last_llm_skip_reason

    rule = _fallback_decision(context)
    use_llm, reason = should_use_llm(context)
    _last_llm_skip_reason = reason

    if not use_llm:
        logger.info("LLM skipped (%s) — using rules/local path", reason)
        if rule:
            rule["decision_source"] = f"rules:{reason}"
        return rule

    provider = settings.llm_provider.lower()
    llm_result = None

    if provider == "claude" and settings.claude_api_key:
        try:
            llm_result = await _call_claude(context, db)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse Claude response: %s", e)
        except Exception as e:
            logger.error("Claude API error: %s", e)
    elif settings.openai_api_key:
        try:
            llm_result = await _call_openai(context, db)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse OpenAI response: %s", e)
        except Exception as e:
            logger.error("OpenAI API error: %s", e)
    else:
        logger.warning("No LLM API key — rules only")
        _last_llm_skip_reason = "no_key"
        if rule:
            rule["decision_source"] = "rules:no_key"
        return rule

    _last_llm_call_at = datetime.utcnow()

    if llm_result:
        llm_result["decision_source"] = f"llm:{reason}"
        return llm_result

    if rule:
        rule["decision_source"] = "rules:llm_fallback"
    return rule


async def get_claude_decision(context: dict, db: Session) -> dict | None:
    return await get_llm_decision(context, db)


def _fallback_decision(context: dict) -> dict | None:
    """Rule-based short-hold signal."""
    signals = context.get("technical_signals", [])
    prices = {p["symbol"]: p for p in context.get("prices", []) if isinstance(p, dict)}

    if not signals:
        return None

    best = max(signals, key=lambda s: abs(s.get("signal_score", 0) if isinstance(s, dict) else 0))
    if not isinstance(best, dict):
        return None
    score = float(best.get("signal_score") or 0)
    if abs(score) < settings.llm_min_signal:
        return None

    symbol = best.get("symbol")
    price_data = prices.get(symbol, {})
    current_price = float(price_data.get("price") or 0)
    if not current_price:
        return None

    direction = "long" if score > 0 else "short"
    decision = {
        "coin": symbol,
        "direction": direction,
        "entry": current_price,
        "take_profit": 0,
        "stop_loss": 0,
        "confidence": min(abs(score), 100),
        "reasoning": (
            f"Rule scalp: RSI={best.get('rsi')}, "
            f"MACD={(best.get('macd') or {}).get('trend')}, score={score:.0f}. "
            f"Max hold {settings.max_hold_minutes}m."
        ),
        "backtest": {"valid": False, "win_rate": 0, "sample_size": 0},
    }
    decision = apply_scalp_levels(decision)
    if float(decision["confidence"]) < settings.min_confidence_to_trade:
        return None
    return decision


def rank_opportunities(context: dict, decisions: list[dict]) -> list[dict]:
    """Score and rank top trade opportunities."""
    scored = []
    for d in decisions:
        if not d:
            continue
        bt = d.get("backtest", {})
        bt_bonus = bt.get("win_rate", 0) * 0.3 if bt.get("valid") else 0
        final_score = d.get("confidence", 0) * 0.7 + bt_bonus
        scored.append({**d, "final_score": round(final_score, 1)})

    scored.sort(key=lambda x: x["final_score"], reverse=True)
    return scored[:3]
