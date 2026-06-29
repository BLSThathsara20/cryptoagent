"""Main agent loop — runs every N minutes (default 5)."""

import asyncio
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from config import settings
from db.session import SessionLocal
from db.models import AgentStatus, AgentDecision
from agent.analyser import build_market_context
from agent.brain import get_claude_decision, rank_opportunities
from agent.executor import execute_trade, check_pending_trades
from agent.fund_manager import run_fund_manager_cycle
from alerts.manager import create_alert

logger = logging.getLogger(__name__)

_agent_task = None
_running = False


def _get_or_create_status(db: Session) -> AgentStatus:
    status = db.query(AgentStatus).first()
    if not status:
        status = AgentStatus(
            status="idle",
            live_mode=settings.live_mode,
            loop_interval=settings.agent_loop_interval,
            max_risk_percent=settings.max_risk_percent,
            watch_coins=settings.watch_coins,
        )
        db.add(status)
        db.commit()
        db.refresh(status)
    return status


def _set_status(db: Session, new_status: str):
    agent_status = _get_or_create_status(db)
    agent_status.status = new_status
    agent_status.updated_at = datetime.utcnow()
    db.commit()


async def run_agent_cycle():
    """Single agent cycle: analyse → backtest → score → decide → execute → log."""
    db = SessionLocal()
    try:
        _set_status(db, "analysing")
        logger.info("Agent cycle started")

        # Build market context (includes fund availability from fund manager)
        fund_result = run_fund_manager_cycle(db)
        logger.info(
            "Fund Manager: %s (portfolio $%.2f)",
            fund_result["decision"]["action"],
            fund_result["portfolio"]["total_usd"],
        )

        check_pending_trades(db)

        context = build_market_context(db)
        context["fund_manager"] = fund_result["decision"]
        context["portfolio"] = {
            "total_usd": fund_result["portfolio"]["total_usd"],
            "available_usd": fund_result["portfolio"]["available_usd"],
            "target_daily_profit": fund_result["decision"]["target_daily_profit"],
        }

        # Get decisions for top watch coins (Claude + fallback)
        decisions = []
        primary = await get_claude_decision(context, db)
        if primary:
            primary["technical_signals"] = context.get("technical_signals")
            decisions.append(primary)

        # Rank opportunities
        ranked = rank_opportunities(context, decisions)
        if not ranked:
            logger.info("No trade opportunities found this cycle")
            create_alert(
                db, "info", "trading", "No Trade This Cycle",
                "Agent analysed market but no setup met confidence threshold. Will retry next cycle.",
            )
            _set_status(db, "idle")
            agent_status = _get_or_create_status(db)
            agent_status.last_run_at = datetime.utcnow()
            db.commit()
            return

        best = ranked[0]
        logger.info(
            "Best opportunity: %s %s (confidence: %s)",
            best["coin"],
            best["direction"],
            best.get("confidence"),
        )

        # Execute trade
        _set_status(db, "running")
        record = execute_trade(db, best)
        if record:
            logger.info("Trade recorded: ID %s", record.id)
            create_alert(
                db, "success", "trading",
                f"Paper Trade: {best['direction'].upper()} {best['coin']}",
                f"Entry ${best['entry']:.2f} · TP ${best['take_profit']:.2f} · SL ${best['stop_loss']:.2f} · Confidence {best.get('confidence', 0)}",
            )

        agent_status = _get_or_create_status(db)
        agent_status.last_run_at = datetime.utcnow()
        agent_status.status = "idle"
        db.commit()
        create_alert(db, "info", "system", "Agent Cycle Complete", "Analysis and fund check finished.")
        logger.info("Agent cycle complete")

    except Exception as e:
        logger.error("Agent cycle failed: %s", e)
        _set_status(db, "idle")
    finally:
        db.close()


async def agent_loop():
    """Continuous agent loop with configurable interval."""
    global _running
    _running = True
    logger.info("Agent loop started (interval: %ds)", settings.agent_loop_interval)

    # Initial delay to let data populate
    await asyncio.sleep(30)

    while _running:
        await run_agent_cycle()
        await asyncio.sleep(settings.agent_loop_interval)


def start_agent_loop():
    """Start the agent loop as an asyncio task."""
    global _agent_task
    loop = asyncio.get_event_loop()
    _agent_task = loop.create_task(agent_loop())
    return _agent_task


def stop_agent_loop():
    """Stop the agent loop."""
    global _running, _agent_task
    _running = False
    if _agent_task and not _agent_task.done():
        _agent_task.cancel()


async def trigger_agent_cycle_now():
    """Manually run one agent cycle (for testing paper trading)."""
    await run_agent_cycle()
