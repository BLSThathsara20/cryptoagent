"""Main agent loop — runs every N minutes (default 5).

Heavy sync work (DB + LLM) runs in a worker thread so the FastAPI event loop
stays free — UI polls (/pulse, prices, etc.) keep updating without page refresh.
"""

import asyncio
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from config import settings
from db.session import SessionLocal
from db.models import AgentStatus
from agent.analyser import build_market_context
from agent.brain import get_claude_decision, rank_opportunities
from agent.executor import execute_trade, check_pending_trades, count_open_trades
from agent.fund_manager import run_fund_manager_cycle
from alerts.manager import create_alert
from analytics.insights import get_daily_targets

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


def _run_agent_cycle_sync() -> dict:
    """
    Sync cycle body (DB + local model). Safe to run in a thread.
    Returns a payload the async layer may use for the LLM step.
    """
    db = SessionLocal()
    try:
        _set_status(db, "preparing")
        logger.info("Agent cycle started")

        _set_status(db, "analysing")
        fund_result = run_fund_manager_cycle(db)
        logger.info(
            "Fund Manager: %s (portfolio $%.2f)",
            fund_result["decision"]["action"],
            fund_result["portfolio"]["total_usd"],
        )

        check_pending_trades(db)

        open_n = count_open_trades(db)
        if open_n >= settings.max_open_trades:
            logger.info("Max open trades reached (%s) — managing exits only", open_n)
            create_alert(
                db, "info", "trading", "Holding Open Trades",
                f"{open_n} open · max {settings.max_open_trades}. Waiting for TP/SL or {settings.max_hold_minutes}m time-exit.",
            )
            agent_status = _get_or_create_status(db)
            agent_status.last_run_at = datetime.utcnow()
            agent_status.status = "monitoring"
            db.commit()
            return {"done": True}

        try:
            targets = get_daily_targets(db, days=7)
            today = targets.get("today") or {}
            if (
                settings.stop_new_trades_when_target_hit
                and today.get("status") == "hit"
            ):
                logger.info("Daily profit target already hit — skipping new entries")
                create_alert(
                    db, "success", "trading", "Daily Target Hit",
                    f"Today P&L ${today.get('pnl', 0):.2f} ≥ target ${targets.get('target_usd', 0):.2f}. Protecting gains.",
                )
                agent_status = _get_or_create_status(db)
                agent_status.last_run_at = datetime.utcnow()
                agent_status.status = "monitoring"
                db.commit()
                return {"done": True}
        except Exception as tgt_err:
            logger.warning("Daily target check skipped: %s", tgt_err)

        context = build_market_context(db)
        context["fund_manager"] = fund_result["decision"]
        context["portfolio"] = {
            "total_usd": fund_result["portfolio"]["total_usd"],
            "available_usd": fund_result["portfolio"]["available_usd"],
            "target_daily_profit": fund_result["decision"]["target_daily_profit"],
        }
        _set_status(db, "deciding")
        # Hand context back; LLM runs on event loop with to_thread for HTTP
        return {"done": False, "context": context}
    except Exception as e:
        logger.error("Agent analyse phase failed: %s", e)
        try:
            db.rollback()
            _set_status(db, "monitoring")
        except Exception as inner:
            logger.error("Failed to reset agent status: %s", inner)
        return {"done": True}
    finally:
        db.close()


def _finish_agent_cycle_sync(best: dict | None, context: dict | None) -> None:
    """Execute trade (if any) and mark cycle complete — runs in a worker thread."""
    db = SessionLocal()
    try:
        if best:
            _set_status(db, "executing")
            record = execute_trade(db, best)
            if record:
                from agent.local_learner import save_decision_snapshot

                try:
                    save_decision_snapshot(db, record, context or {}, best)
                except Exception as snap_err:
                    logger.warning("Feature snapshot save failed: %s", snap_err)
                logger.info("Trade recorded: ID %s", record.id)
                create_alert(
                    db, "success", "trading",
                    f"Paper Trade: {best['direction'].upper()} {best['coin']}",
                    f"Entry ${best['entry']:.2f} · TP ${best['take_profit']:.2f} · "
                    f"SL ${best['stop_loss']:.2f} · Confidence {best.get('confidence', 0)}",
                )
        elif context is None and best is None:
            pass

        agent_status = _get_or_create_status(db)
        agent_status.last_run_at = datetime.utcnow()
        agent_status.status = "monitoring"
        db.commit()
        create_alert(db, "info", "system", "Agent Cycle Complete", "Analysis and fund check finished.")
        logger.info("Agent cycle complete")
    except Exception as e:
        logger.error("Agent finish phase failed: %s", e)
        try:
            db.rollback()
            _set_status(db, "monitoring")
        except Exception as inner:
            logger.error("Failed to reset agent status: %s", inner)
    finally:
        db.close()


def _blend_local_score_sync(context: dict, primary: dict) -> dict:
    db = SessionLocal()
    try:
        from agent.local_learner import extract_features, score_setup, _get_weights

        feats = extract_features(context, primary)
        local_score = score_setup(db, feats)
        primary["local_model_score"] = round(local_score, 1)
        samples = int((_get_weights(db).samples or 0))
        if samples >= 5:
            blend = min(0.35, 0.1 + samples * 0.005)
            llm_c = float(primary.get("confidence") or 0)
            primary["confidence"] = round(llm_c * (1 - blend) + local_score * blend, 1)
            primary["reasoning"] = (
                f"{primary.get('reasoning', '')} "
                f"[Local model v-blend: score={local_score:.0f}, samples={samples}, weight={blend:.0%}]"
            ).strip()
        return primary
    except Exception as blend_err:
        logger.warning("Local model blend skipped: %s", blend_err)
        return primary
    finally:
        db.close()


async def run_agent_cycle():
    """Single agent cycle — keeps the asyncio loop free for HTTP/UI."""
    phase = await asyncio.to_thread(_run_agent_cycle_sync)
    if phase.get("done"):
        return

    context = phase.get("context") or {}
    db = SessionLocal()
    try:
        primary = await get_claude_decision(context, db)
    finally:
        db.close()

    decisions = []
    if primary:
        primary["technical_signals"] = context.get("technical_signals")
        primary = await asyncio.to_thread(_blend_local_score_sync, context, primary)
        decisions.append(primary)

    ranked = rank_opportunities(context, decisions)
    if not ranked:
        logger.info("No trade opportunities found this cycle")

        def _no_trade():
            db2 = SessionLocal()
            try:
                create_alert(
                    db2, "info", "trading", "No Trade This Cycle",
                    "Agent analysed market but no setup met confidence threshold. Will retry next cycle.",
                )
                agent_status = _get_or_create_status(db2)
                agent_status.last_run_at = datetime.utcnow()
                agent_status.status = "monitoring"
                db2.commit()
            finally:
                db2.close()

        await asyncio.to_thread(_no_trade)
        return

    best = ranked[0]
    logger.info(
        "Best opportunity: %s %s (confidence: %s)",
        best["coin"],
        best["direction"],
        best.get("confidence"),
    )
    await asyncio.to_thread(_finish_agent_cycle_sync, best, context)


async def agent_loop(boot_delay_sec: float = 30):
    """Continuous agent loop with configurable interval."""
    global _running
    _running = True
    logger.info(
        "Agent loop started (interval: %ds, boot_delay: %ss)",
        settings.agent_loop_interval,
        boot_delay_sec,
    )

    def _boot():
        db = SessionLocal()
        try:
            _set_status(db, "preparing")
        finally:
            db.close()

    await asyncio.to_thread(_boot)
    if boot_delay_sec > 0:
        await asyncio.sleep(boot_delay_sec)

    while _running:
        try:
            await run_agent_cycle()
        except Exception as e:
            logger.error("Agent loop iteration crashed: %s", e)

        def _idle():
            db = SessionLocal()
            try:
                _set_status(db, "monitoring")
            finally:
                db.close()

        await asyncio.to_thread(_idle)
        await asyncio.sleep(settings.agent_loop_interval)


def start_agent_loop(boot_delay_sec: float = 30):
    """Start the agent loop as an asyncio task."""
    global _agent_task, _running
    _running = True
    _agent_task = asyncio.create_task(agent_loop(boot_delay_sec=boot_delay_sec))
    return _agent_task


def ensure_agent_loop_running(boot_delay_sec: float = 5) -> bool:
    """
    Respawn the agent loop if the asyncio task died.
    Returns True if a new task was started.
    """
    global _agent_task, _running
    if _agent_task is not None and not _agent_task.done():
        return False
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("Cannot respawn agent loop — no running event loop")
        return False
    _running = True
    _agent_task = asyncio.create_task(agent_loop(boot_delay_sec=boot_delay_sec))
    logger.info("Agent loop task respawned (was dead/overdue)")
    return True


def restart_agent_loop(boot_delay_sec: float = 2) -> dict:
    """
    Force-restart the agent loop (cancel old task, start fresh).
    Used after offline recovery and by the manual Restart button.
    """
    global _agent_task, _running
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return {"ok": False, "message": "No event loop — restart from backend process"}

    was_alive = _agent_task is not None and not _agent_task.done()
    _running = False
    if _agent_task is not None and not _agent_task.done():
        _agent_task.cancel()
    _agent_task = None
    _running = True
    _agent_task = asyncio.create_task(agent_loop(boot_delay_sec=boot_delay_sec))
    logger.info("Agent loop force-restarted (was_alive=%s)", was_alive)
    return {
        "ok": True,
        "was_alive": was_alive,
        "loop_running": True,
        "boot_delay_sec": boot_delay_sec,
        "message": "Agent loop restarted",
    }


def stop_agent_loop():
    """Stop the agent loop."""
    global _running, _agent_task
    _running = False
    if _agent_task and not _agent_task.done():
        _agent_task.cancel()
    _agent_task = None


def is_agent_loop_running() -> bool:
    """True while the autonomous agent loop task is active."""
    if not _running:
        return False
    if _agent_task is None:
        return True
    return not _agent_task.done()


async def trigger_agent_cycle_now():
    """Manually run one agent cycle (for testing paper trading)."""
    await run_agent_cycle()
