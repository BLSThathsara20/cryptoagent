"""Validation Agent — health checks, accuracy validation, issue detection."""

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from sqlalchemy import desc

from config import settings
from db.session import SessionLocal
from db.models import (
    AgentDecision,
    AgentStatus,
    AgentMemory,
    PaperAccount,
    SystemIssue,
    ValidationRun,
    CoinPrice,
)
from data.binance_ws import get_ws_status
from data.ingestion import get_ingestion_status
from data.retention import get_database_stats
from agent.binance_client import is_configured, diagnose_binance
from agent.llm_usage import test_openai_connection, get_current_month_spend
from alerts.manager import create_alert

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_last_run: datetime | None = None


def _add_check(checks: list, name: str, passed: bool, message: str, category: str = "system"):
    checks.append({
        "name": name,
        "status": "pass" if passed else "fail",
        "message": message,
        "category": category,
    })
    return passed


def _upsert_issue(
    db: Session,
    category: str,
    severity: str,
    title: str,
    message: str,
    source: str = "validator",
):
    """Create issue if same title not already open."""
    existing = (
        db.query(SystemIssue)
        .filter(SystemIssue.title == title, SystemIssue.resolved == False)  # noqa: E712
        .first()
    )
    if existing:
        existing.message = message
        existing.severity = severity
        return existing
    issue = SystemIssue(
        category=category,
        severity=severity,
        title=title,
        message=message,
        source=source,
    )
    db.add(issue)
    return issue


def _resolve_issue(db: Session, title: str):
    """Remove open issues when check passes — no DB clutter."""
    db.query(SystemIssue).filter(
        SystemIssue.title == title,
        SystemIssue.resolved == False,  # noqa: E712
    ).delete(synchronize_session=False)


def compute_accuracy_score(db: Session) -> tuple[float, str]:
    """Trade decision accuracy from closed trades."""
    closed = (
        db.query(AgentDecision)
        .filter(AgentDecision.status.in_(["win", "loss"]))
        .order_by(desc(AgentDecision.closed_at))
        .limit(50)
        .all()
    )
    if not closed:
        return 0.0, "No closed trades yet — accuracy unavailable"

    wins = sum(1 for t in closed if t.status == "win")
    score = wins / len(closed) * 100
    return round(score, 1), f"{wins}/{len(closed)} recent trades profitable ({score:.0f}% win rate)"


def run_validation(db: Session | None = None) -> dict:
    """Run all validation checks and persist results."""
    global _last_run
    _last_run = datetime.utcnow()
    own_session = db is None
    if own_session:
        db = SessionLocal()

    checks: list[dict] = []
    issues_found = 0

    try:
        # Database
        try:
            db_stats = get_database_stats(db)
            size_mb = db_stats.get("database_size_mb", 0)
            ok = _add_check(checks, "Database connection", True, f"Connected ({size_mb} MB)", "system")
            if size_mb > settings.db_size_warn_mb:
                _add_check(checks, "Database size", False, f"DB {size_mb} MB exceeds {settings.db_size_warn_mb} MB warn threshold", "system")
                _upsert_issue(db, "system", "warning", "Database Size High", f"Database is {size_mb} MB. Auto-cleanup is running.")
                issues_found += 1
            else:
                _add_check(checks, "Database size", True, f"{size_mb} MB — within limits", "system")
                _resolve_issue(db, "Database Size High")
        except Exception as e:
            _add_check(checks, "Database connection", False, str(e), "system")
            _upsert_issue(db, "system", "critical", "Database Unavailable", str(e))
            issues_found += 1

        # Binance WebSocket
        ws = get_ws_status()
        ws_ok = ws.get("status") == "connected"
        _add_check(checks, "Binance WebSocket", ws_ok, ws.get("status", "unknown"), "data")
        if not ws_ok:
            _upsert_issue(db, "data", "warning", "WebSocket Disconnected", "Market stream reconnecting automatically.")
            issues_found += 1
        else:
            _resolve_issue(db, "WebSocket Disconnected")

        # Data ingestion
        ingestion = get_ingestion_status()
        ing_ok = ingestion.get("running", False)
        _add_check(checks, "Data ingestion", ing_ok, "Running" if ing_ok else "Stopped", "data")

        # Fresh market prices
        latest_price = db.query(CoinPrice).order_by(desc(CoinPrice.timestamp)).first()
        if latest_price and latest_price.timestamp:
            age = (datetime.utcnow() - latest_price.timestamp.replace(tzinfo=None)).total_seconds()
            fresh = age < 300
            _add_check(checks, "Market data freshness", fresh, f"Last price {int(age)}s ago", "data")
            if not fresh:
                _upsert_issue(db, "data", "warning", "Stale Market Data", f"No new prices in {int(age // 60)} minutes.")
                issues_found += 1
            else:
                _resolve_issue(db, "Stale Market Data")
        else:
            _add_check(checks, "Market data freshness", False, "No price data", "data")
            issues_found += 1

        # Binance — market (public) vs account (private). Paper mode: account fail is warning only.
        diag = diagnose_binance(force=True)
        if diag.get("market_ok"):
            _add_check(checks, "Binance market", True, "Public market reachable", "binance")
        else:
            _add_check(checks, "Binance market", False, diag.get("message", "Unreachable"), "binance")
            issues_found += 1

        if is_configured():
            if diag.get("account_ok"):
                _add_check(checks, "Binance account", True, diag.get("message", "Connected"), "binance")
                _resolve_issue(db, "Binance API Failed")
                _resolve_issue(db, "Binance Account API")
            elif not settings.live_mode:
                # Paper mode: account/IP glitches must not open Issues or degrade health
                _add_check(
                    checks,
                    "Binance account",
                    True,
                    "Paper mode OK — account API has a glitch (IP/key). Live trading still blocked until fixed.",
                    "binance",
                )
                _resolve_issue(db, "Binance API Failed")
                _resolve_issue(db, "Binance Account API")
            else:
                _add_check(
                    checks, "Binance account", False,
                    diag.get("hint") or diag.get("message") or "Account API failed",
                    "binance",
                )
                _upsert_issue(
                    db, "binance", "error", "Binance Account API",
                    diag.get("hint") or "Check API key permissions and IP whitelist.",
                )
                issues_found += 1
        else:
            _add_check(checks, "Binance account", True, "Not configured (paper mode OK)", "binance")
            _resolve_issue(db, "Binance Account API")
            _resolve_issue(db, "Binance API Failed")

        # OpenAI / LLM
        if settings.llm_configured:
            if settings.llm_provider == "openai":
                test = test_openai_connection()
                llm_ok = test.get("status") == "connected"
                _add_check(checks, "OpenAI API", llm_ok, test.get("message", ""), "llm")
                if not llm_ok:
                    _upsert_issue(db, "llm", "error", "OpenAI API Error", test.get("message", "Connection failed"))
                    issues_found += 1
                else:
                    _resolve_issue(db, "OpenAI API Error")
            else:
                _add_check(checks, "LLM provider", True, f"{settings.llm_provider} configured", "llm")

            spend = get_current_month_spend(db)
            budget_ok = spend < settings.llm_monthly_budget_usd
            _add_check(
                checks, "AI budget",
                budget_ok,
                f"${spend:.2f} / ${settings.llm_monthly_budget_usd} this month",
                "llm",
            )
            if not budget_ok:
                _upsert_issue(db, "llm", "warning", "AI Budget Exceeded", "Agent using rule-based signals until next month.")
                issues_found += 1
            else:
                _resolve_issue(db, "AI Budget Exceeded")
        else:
            _add_check(checks, "LLM provider", False, "No API key — rule-based mode only", "llm")

        # Agent loop
        agent = db.query(AgentStatus).first()
        from agent.loop import is_agent_loop_running

        loop_alive = is_agent_loop_running()
        if agent and agent.last_run_at:
            gap = (datetime.utcnow() - agent.last_run_at.replace(tzinfo=None)).total_seconds()
            agent_ok = gap < settings.agent_loop_interval * 3 and loop_alive
            msg = f"Last run {int(gap)}s ago"
            if not loop_alive:
                msg += " — loop task dead (auto-recovery will restart)"
            _add_check(checks, "Agent loop", agent_ok, msg, "agent")
            if not agent_ok:
                _upsert_issue(db, "agent", "warning", "Agent Overdue", f"Last cycle {int(gap // 60)} min ago.")
                issues_found += 1
            else:
                _resolve_issue(db, "Agent Overdue")
        elif not loop_alive:
            _add_check(checks, "Agent loop", False, "Loop task not running", "agent")
            _upsert_issue(db, "agent", "warning", "Agent Overdue", "Agent loop task stopped — recovery will restart it.")
            issues_found += 1
        else:
            _add_check(checks, "Agent loop", False, "Never run", "agent")

        # Paper account drawdown
        account = db.query(PaperAccount).first()
        if account and account.max_drawdown > 15:
            _add_check(checks, "Drawdown limit", False, f"Max drawdown {account.max_drawdown:.1f}%", "trading")
            _upsert_issue(db, "trading", "warning", "High Drawdown", f"Paper account drawdown at {account.max_drawdown:.1f}%.")
            issues_found += 1
        elif account:
            _add_check(checks, "Drawdown limit", True, f"Max drawdown {account.max_drawdown:.1f}%", "trading")
            _resolve_issue(db, "High Drawdown")

        # Trade accuracy
        accuracy, acc_msg = compute_accuracy_score(db)
        acc_ok = accuracy >= 40 or accuracy == 0
        _add_check(checks, "Trade accuracy", acc_ok, acc_msg, "trading")
        if accuracy > 0 and accuracy < 40:
            _upsert_issue(db, "trading", "warning", "Low Win Rate", acc_msg)
            issues_found += 1
        elif accuracy >= 40:
            _resolve_issue(db, "Low Win Rate")

        # Learning pipeline + regime
        mem_count = db.query(AgentMemory).count()
        _add_check(checks, "Learning pipeline", True, f"{mem_count} lessons stored", "agent")

        from agent.regime import get_latest_regime, get_learning_drift
        regime = get_latest_regime(db)
        drift = get_learning_drift(db)
        if regime:
            regime_ok = regime.get("allow_new_trades", True)
            _add_check(
                checks, "Market regime",
                regime_ok,
                f"{regime.get('regime_label')} · size ×{regime.get('size_multiplier', 1)}",
                "trading",
            )
            if not regime_ok:
                _upsert_issue(
                    db, "trading", "warning", "Regime Pause Active",
                    "; ".join(regime.get("policy_notes") or ["New entries paused"]),
                )
                issues_found += 1
            elif regime.get("regime_shifted"):
                _upsert_issue(
                    db, "trading", "info", "Regime Shift Detected",
                    f"Now {regime.get('regime_label')} — size reduced until stable",
                )
            else:
                _resolve_issue(db, "Regime Pause Active")
                _resolve_issue(db, "Regime Shift Detected")
        if drift.get("drift_detected"):
            _add_check(
                checks, "Learning drift",
                False,
                f"{drift.get('negative_streak_days')}d negative learning rate",
                "agent",
            )
            _upsert_issue(
                db, "agent", "warning", "Learning Drift",
                "Daily accuracy falling — stale lessons down-weighted, size reduced",
            )
            issues_found += 1
        else:
            _add_check(checks, "Learning drift", True, "Learning rate stable", "agent")
            _resolve_issue(db, "Learning Drift")

        # Live mode readiness
        if settings.live_mode:
            live_ready = is_configured() and settings.llm_configured
            _add_check(checks, "Live trading mode", live_ready, "LIVE — real orders enabled" if live_ready else "LIVE but missing keys", "trading")
            if not live_ready:
                _upsert_issue(db, "trading", "critical", "Live Mode Misconfigured", "Live mode on but Binance or LLM not ready.")
                issues_found += 1
            else:
                _resolve_issue(db, "Live Mode Misconfigured")
        else:
            _add_check(checks, "Live trading mode", True, "Paper/mock mode — safe", "trading")

        passed = sum(1 for c in checks if c["status"] == "pass")
        failed = sum(1 for c in checks if c["status"] == "fail")

        if failed == 0:
            overall = "healthy"
        elif failed <= 2:
            overall = "degraded"
        else:
            overall = "critical"

        health_score = round(passed / max(len(checks), 1) * 100, 1)

        run = ValidationRun(
            overall_status=overall,
            health_score=health_score,
            checks_passed=passed,
            checks_failed=failed,
            accuracy_score=accuracy,
            checks=checks,
        )
        db.add(run)
        db.commit()

        if overall == "critical":
            create_alert(db, "error", "system", "Validation Critical", f"{failed} checks failed. See Issues page.", commit=True)

        return {
            "overall_status": overall,
            "health_score": health_score,
            "accuracy_score": accuracy,
            "checks_passed": passed,
            "checks_failed": failed,
            "issues_found": issues_found,
            "checks": checks,
            "last_run_at": _last_run.isoformat(),
        }
    except Exception as e:
        logger.error("Validation run failed: %s", e)
        if own_session:
            db.rollback()
        raise
    finally:
        if own_session:
            db.close()


def get_open_issues(db: Session) -> list[SystemIssue]:
    return (
        db.query(SystemIssue)
        .filter(SystemIssue.resolved == False)  # noqa: E712
        .order_by(desc(SystemIssue.created_at))
        .all()
    )


def get_issues_summary(db: Session) -> dict:
    """All issues for Issues page."""
    open_issues = get_open_issues(db)
    recent_runs = (
        db.query(ValidationRun)
        .order_by(desc(ValidationRun.created_at))
        .limit(5)
        .all()
    )
    latest = recent_runs[0] if recent_runs else None

    from autopilot.scheduler import get_autopilot_status
    autopilot = get_autopilot_status(db)

    return {
        "overall_status": latest.overall_status if latest else "unknown",
        "health_score": latest.health_score if latest else 0,
        "accuracy_score": latest.accuracy_score if latest else 0,
        "last_validation_at": _last_run.isoformat() if _last_run else (latest.created_at.isoformat() if latest and latest.created_at else None),
        "open_count": len(open_issues),
        "critical_count": sum(1 for i in open_issues if i.severity == "critical"),
        "warning_count": sum(1 for i in open_issues if i.severity in ("warning", "error")),
        "open_issues": [
            {
                "id": i.id,
                "category": i.category,
                "severity": i.severity,
                "title": i.title,
                "message": i.message,
                "source": i.source,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in open_issues
        ],
        "recent_validations": [
            {
                "id": r.id,
                "overall_status": r.overall_status,
                "health_score": r.health_score,
                "accuracy_score": r.accuracy_score,
                "checks_passed": r.checks_passed,
                "checks_failed": r.checks_failed,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recent_runs
        ],
        "latest_checks": latest.checks if latest else [],
        "autopilot_issues": autopilot.get("issues", []),
    }


async def scheduled_validation():
    db = SessionLocal()
    try:
        run_validation(db)
        from agent.loop import ensure_agent_loop_running, is_agent_loop_running, trigger_agent_cycle_now

        if not is_agent_loop_running():
            if ensure_agent_loop_running():
                create_alert(
                    db, "warning", "system", "Agent Loop Restarted",
                    "Agent loop task had stopped — restarted automatically.",
                    commit=True,
                )
        # If overdue but task alive, kick a cycle (existing autopilot path also covers this)
        agent = db.query(AgentStatus).first()
        if agent and agent.last_run_at and settings.auto_recovery_enabled:
            gap = (datetime.utcnow() - agent.last_run_at.replace(tzinfo=None)).total_seconds()
            if gap > settings.agent_loop_interval * 3:
                await trigger_agent_cycle_now()
        logger.info("Validation agent completed")
    except Exception as e:
        logger.error("Scheduled validation failed: %s", e)
    finally:
        db.close()


def start_validation_scheduler():
    scheduler.add_job(
        scheduled_validation,
        "interval",
        minutes=5,
        id="validation_agent",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
    logger.info("Validation agent scheduler started (every 5 min)")


def stop_validation_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
