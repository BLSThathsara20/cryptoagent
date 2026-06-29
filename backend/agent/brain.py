"""LLM integration for trading decisions — OpenAI (default) or Claude."""

import json
import logging

import anthropic
from openai import OpenAI
from sqlalchemy.orm import Session

from config import settings
from agent.analyser import backtest_setup

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert crypto trading analyst AI. Analyse the provided market data and return a structured trading decision.

Rules:
- Always include stop_loss — never recommend a trade without one
- Risk/reward ratio should be at least 1:2 (TP distance >= 2x SL distance)
- Consider fear/greed index, liquidations, long/short ratios, and order book imbalance
- Combine technical signals with macro sentiment
- Learn from past_lessons if provided — avoid repeating losing patterns
- Return ONLY valid JSON, no markdown

Response format:
{
  "coin": "BTC",
  "direction": "long" or "short",
  "entry": 95000.0,
  "take_profit": 98000.0,
  "stop_loss": 93500.0,
  "confidence": 75,
  "reasoning": "Detailed explanation..."
}"""


def _build_user_message(context: dict) -> str:
    return f"""Analyse this market data and recommend the best trade setup:

{json.dumps(context, indent=2, default=str)}

Watch coins: {context.get('watch_coins', [])}
Provide your top trade recommendation with full reasoning."""


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
    bt = backtest_setup(db, decision["coin"], decision["direction"])
    decision["backtest"] = bt
    return decision


async def _call_openai(context: dict, db: Session) -> dict | None:
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.openai_model,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(context)},
        ],
        response_format={"type": "json_object"},
    )
    text = response.choices[0].message.content or ""
    decision = _parse_decision(text)
    return _validate_decision(decision, db)


async def _call_claude(context: dict, db: Session) -> dict | None:
    client = anthropic.Anthropic(api_key=settings.claude_api_key)
    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_message(context)}],
    )
    text = response.content[0].text.strip()
    decision = _parse_decision(text)
    return _validate_decision(decision, db)


async def get_llm_decision(context: dict, db: Session) -> dict | None:
    """Call configured LLM provider and return structured decision."""
    provider = settings.llm_provider.lower()

    if provider == "claude" and settings.claude_api_key:
        try:
            result = await _call_claude(context, db)
            if result:
                return result
        except json.JSONDecodeError as e:
            logger.error("Failed to parse Claude response: %s", e)
        except Exception as e:
            logger.error("Claude API error: %s", e)

    elif settings.openai_api_key:
        try:
            result = await _call_openai(context, db)
            if result:
                return result
        except json.JSONDecodeError as e:
            logger.error("Failed to parse OpenAI response: %s", e)
        except Exception as e:
            logger.error("OpenAI API error: %s", e)

    elif provider == "claude" and not settings.claude_api_key:
        logger.warning("LLM_PROVIDER=claude but CLAUDE_API_KEY not set")
    else:
        logger.warning("No LLM API key configured — using rule-based fallback")

    return _fallback_decision(context)


# Backward-compatible alias
async def get_claude_decision(context: dict, db: Session) -> dict | None:
    return await get_llm_decision(context, db)


def _fallback_decision(context: dict) -> dict | None:
    """Rule-based fallback when LLM is unavailable."""
    signals = context.get("technical_signals", [])
    prices = {p["symbol"]: p for p in context.get("prices", [])}

    if not signals:
        return None

    best = max(signals, key=lambda s: abs(s.get("signal_score", 0)))
    score = best.get("signal_score", 0)
    if abs(score) < 20:
        return None

    symbol = best["symbol"]
    price_data = prices.get(symbol, {})
    current_price = price_data.get("price", 0)
    if not current_price:
        return None

    direction = "long" if score > 0 else "short"
    sl_pct = 0.02
    tp_pct = 0.04

    if direction == "long":
        stop_loss = current_price * (1 - sl_pct)
        take_profit = current_price * (1 + tp_pct)
    else:
        stop_loss = current_price * (1 + sl_pct)
        take_profit = current_price * (1 - tp_pct)

    return {
        "coin": symbol,
        "direction": direction,
        "entry": current_price,
        "take_profit": round(take_profit, 4),
        "stop_loss": round(stop_loss, 4),
        "confidence": min(abs(score), 100),
        "reasoning": f"Rule-based signal: RSI={best.get('rsi')}, MACD trend={best.get('macd', {}).get('trend')}, score={score}",
        "backtest": {"valid": False, "win_rate": 0, "sample_size": 0},
    }


def rank_opportunities(context: dict, decisions: list[dict]) -> list[dict]:
    """Score and rank top 3 trade opportunities."""
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
