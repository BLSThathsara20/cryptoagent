"""Analytics: P&L, wealth growth, predictions, and learning digests."""

from datetime import datetime, timedelta
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import desc

from config import settings
from db.models import (
    AgentDecision,
    AgentMemory,
    PaperAccount,
    PaperPnLHistory,
    PortfolioSnapshot,
    FundManagerDecision,
)


def _day_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _today_start() -> datetime:
    now = datetime.utcnow()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def get_daily_pnl(db: Session, days: int = 30) -> dict:
    """Aggregate closed trade P&L by calendar day."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    trades = (
        db.query(AgentDecision)
        .filter(AgentDecision.closed_at.isnot(None))
        .filter(AgentDecision.closed_at >= cutoff)
        .all()
    )

    by_day: dict[str, dict] = defaultdict(lambda: {"pnl": 0.0, "wins": 0, "losses": 0, "trades": 0})
    for t in trades:
        if not t.closed_at:
            continue
        key = _day_key(t.closed_at)
        by_day[key]["pnl"] += t.outcome_pnl or 0
        by_day[key]["trades"] += 1
        if t.status == "win":
            by_day[key]["wins"] += 1
        elif t.status == "loss":
            by_day[key]["losses"] += 1

    today = _day_key(datetime.utcnow())
    today_data = by_day.get(today, {"pnl": 0.0, "wins": 0, "losses": 0, "trades": 0})

    # Fill series for chart (include zero days)
    series = []
    for i in range(days - 1, -1, -1):
        d = datetime.utcnow() - timedelta(days=i)
        key = _day_key(d)
        row = by_day.get(key, {"pnl": 0.0, "wins": 0, "losses": 0, "trades": 0})
        series.append({
            "date": key,
            "pnl": round(row["pnl"], 2),
            "wins": row["wins"],
            "losses": row["losses"],
            "trades": row["trades"],
        })

    cumulative = 0.0
    for row in series:
        cumulative += row["pnl"]
        row["cumulative_pnl"] = round(cumulative, 2)

    return {
        "today": {
            "date": today,
            "pnl": round(today_data["pnl"], 2),
            "wins": today_data["wins"],
            "losses": today_data["losses"],
            "trades": today_data["trades"],
        },
        "series": series,
    }


def get_daily_targets(db: Session, days: int = 30) -> dict:
    """
    Daily profit target vs realized closed-trade P&L.
    Hit = day's closed P&L >= target for that day.
    """
    paper = db.query(PaperAccount).first()
    portfolio = float(paper.balance) if paper and paper.balance else float(settings.starting_balance)
    # Fallback to snapshot / starting balance if paper looks empty but system started with capital
    if portfolio <= 0:
        portfolio = float(settings.starting_balance)

    target_pct = settings.daily_profit_target_percent
    target_usd = round(portfolio * (target_pct / 100), 2)

    # Prefer latest fund-manager target only if it's in a sane range vs portfolio
    fm = (
        db.query(FundManagerDecision)
        .order_by(desc(FundManagerDecision.created_at))
        .first()
    )
    if fm and fm.target_daily_profit:
        fm_target = float(fm.target_daily_profit)
        # Ignore tiny/corrupt FM targets (e.g. leftover bad rows)
        if fm_target >= target_usd * 0.5 and fm_target <= target_usd * 2.0:
            target_usd = round(fm_target, 2)

    daily = get_daily_pnl(db, days=days)
    today_key = _day_key(datetime.utcnow())
    history = []
    hits = 0
    misses = 0

    for row in daily["series"]:
        pnl = float(row["pnl"] or 0)
        is_today = row["date"] == today_key
        hit = pnl >= target_usd
        if is_today:
            status = "hit" if hit else "in_progress"
        elif row["trades"] == 0:
            status = "no_trade"
        else:
            status = "hit" if hit else "missed"
            if hit:
                hits += 1
            else:
                misses += 1
        history.append({
            "date": row["date"],
            "pnl": pnl,
            "target_usd": target_usd,
            "target_percent": target_pct,
            "progress_percent": round(min(100, (pnl / target_usd * 100)) if target_usd > 0 else 0, 1),
            "hit": hit and row["trades"] > 0,
            "status": status,
            "wins": row["wins"],
            "losses": row["losses"],
            "trades": row["trades"],
            "is_today": is_today,
        })

    today_row = next((h for h in history if h["is_today"]), None)
    past = [h for h in history if not h["is_today"] and h["status"] in ("hit", "missed")]
    hit_rate = round((hits / len(past) * 100), 1) if past else 0.0

    return {
        "target_usd": target_usd,
        "target_percent": target_pct,
        "portfolio_usd": round(portfolio, 2),
        "today": today_row,
        "history": list(reversed(history)),  # newest first for UI
        "stats": {
            "days": len(past),
            "hits": hits,
            "misses": misses,
            "hit_rate_percent": hit_rate,
        },
    }


def get_wealth_growth(db: Session, days: int = 30) -> dict:
    """Portfolio value over time from snapshots and paper balance history."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    snapshots = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.created_at >= cutoff)
        .order_by(PortfolioSnapshot.created_at)
        .all()
    )
    pnl_rows = (
        db.query(PaperPnLHistory)
        .filter(PaperPnLHistory.timestamp >= cutoff)
        .order_by(PaperPnLHistory.timestamp)
        .all()
    )
    account = db.query(PaperAccount).first()

    initial = account.initial_balance if account else settings.starting_balance
    current = account.balance if account else settings.starting_balance
    total_pnl = account.total_pnl if account else 0.0

    # Prefer snapshot totals; fallback to pnl history balances
    wealth_series = []
    if snapshots:
        for s in snapshots:
            wealth_series.append({
                "timestamp": s.created_at.isoformat() if s.created_at else None,
                "value": round(s.total_usd, 2),
                "source": s.source,
            })
    elif pnl_rows:
        for r in pnl_rows:
            wealth_series.append({
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "value": round(r.balance, 2),
                "source": "paper",
            })
    else:
        wealth_series.append({
            "timestamp": datetime.utcnow().isoformat(),
            "value": round(current, 2),
            "source": "paper",
        })

    growth_pct = ((current - initial) / initial * 100) if initial else 0

    return {
        "initial_balance": round(initial, 2),
        "current_balance": round(current, 2),
        "total_pnl": round(total_pnl, 2),
        "growth_percent": round(growth_pct, 2),
        "series": wealth_series,
    }


def get_wealth_predictions(db: Session) -> dict:
    """Simple projections from recent daily performance."""
    daily = get_daily_pnl(db, days=14)
    series = daily["series"]
    non_zero = [s for s in series if s["trades"] > 0]

    if len(non_zero) >= 3:
        avg_daily = sum(s["pnl"] for s in non_zero) / len(non_zero)
    elif series:
        avg_daily = sum(s["pnl"] for s in series) / max(len(series), 1)
    else:
        avg_daily = 0.0

    account = db.query(PaperAccount).first()
    current = account.balance if account else settings.starting_balance
    target_daily = current * (settings.daily_profit_target_percent / 100)

    projections = []
    for label, days in [("7 days", 7), ("30 days", 30), ("90 days", 90)]:
        projected_pnl = avg_daily * days
        projected_value = current + projected_pnl
        projections.append({
            "horizon": label,
            "days": days,
            "projected_pnl": round(projected_pnl, 2),
            "projected_balance": round(projected_value, 2),
            "based_on_avg_daily": round(avg_daily, 2),
        })

    latest_fm = db.query(FundManagerDecision).order_by(desc(FundManagerDecision.created_at)).first()

    return {
        "avg_daily_pnl": round(avg_daily, 2),
        "target_daily_profit": round(latest_fm.target_daily_profit, 2) if latest_fm and latest_fm.target_daily_profit else round(target_daily, 2),
        "target_daily_percent": settings.daily_profit_target_percent,
        "projections": projections,
        "disclaimer": "Projections use recent average daily P&L — not financial advice.",
    }


def get_learnings(db: Session, days: int = 30) -> dict:
    """Agent memories grouped by date with learning status."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    memories = (
        db.query(AgentMemory)
        .filter(AgentMemory.created_at >= cutoff)
        .order_by(desc(AgentMemory.created_at))
        .all()
    )

    today = _day_key(datetime.utcnow())
    today_memories = []
    by_date: dict[str, list] = defaultdict(list)

    for m in memories:
        key = _day_key(m.created_at) if m.created_at else "unknown"
        item = {
            "id": m.id,
            "coin": m.coin,
            "direction": m.direction,
            "outcome": m.outcome,
            "pnl": round(m.pnl, 2) if m.pnl is not None else None,
            "lesson": m.lesson,
            "time": m.created_at.isoformat() if m.created_at else None,
        }
        by_date[key].append(item)
        if key == today:
            today_memories.append(item)

    daily_digest = []
    for date_key in sorted(by_date.keys(), reverse=True):
        items = by_date[date_key]
        wins = sum(1 for i in items if i["outcome"] == "win")
        losses = sum(1 for i in items if i["outcome"] == "loss")
        daily_digest.append({
            "date": date_key,
            "lessons_count": len(items),
            "wins": wins,
            "losses": losses,
            "lessons": items,
        })

    total = len(memories)
    win_lessons = sum(1 for m in memories if m.outcome == "win")
    loss_lessons = sum(1 for m in memories if m.outcome == "loss")

    if total == 0:
        status = "idle"
        status_label = "Waiting for closed trades"
    elif today_memories:
        status = "active"
        status_label = f"Learned {len(today_memories)} lesson(s) today"
    else:
        status = "stable"
        status_label = "No new lessons today — using past experience"

    today_pnl = get_daily_pnl(db, days=2).get("today") or {}
    lesson_pnl = sum((i["pnl"] or 0) for i in today_memories)
    raw = today_pnl.get("pnl")
    live_pnl = float(raw) if raw is not None else float(lesson_pnl)

    return {
        "status": status,
        "status_label": status_label,
        "total_lessons": total,
        "win_lessons": win_lessons,
        "loss_lessons": loss_lessons,
        "today": {
            "date": today,
            "count": len(today_memories),
            "lessons": today_memories,
            "pnl": round(live_pnl, 2),
            "wins": int(today_pnl.get("wins") or 0),
            "losses": int(today_pnl.get("losses") or 0),
            "trades": int(today_pnl.get("trades") or 0),
        },
        "daily_digest": daily_digest,
    }


def get_trading_overview(db: Session) -> dict:
    """Mock vs live mode and performance summary."""
    from db.models import AgentStatus

    status = db.query(AgentStatus).first()
    live_mode = status.live_mode if status else settings.live_mode
    account = db.query(PaperAccount).first()

    closed = db.query(AgentDecision).filter(AgentDecision.status.in_(["win", "loss"])).all()
    wins = sum(1 for t in closed if t.status == "win")
    losses = sum(1 for t in closed if t.status == "loss")
    total_closed = wins + losses
    win_rate = (wins / total_closed * 100) if total_closed else 0
    total_pnl = sum(t.outcome_pnl or 0 for t in closed)

    from agent.binance_client import is_configured

    return {
        "live_mode": live_mode,
        "trading_mode": "live" if live_mode else "paper",
        "trading_mode_label": "Live Trading" if live_mode else "Mock Trading (Paper)",
        "binance_configured": is_configured(),
        "can_enable_live": is_configured() and settings.llm_configured,
        "paper_balance": round(account.balance, 2) if account else settings.starting_balance,
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 1),
        "closed_trades": total_closed,
        "pending_trades": db.query(AgentDecision).filter(AgentDecision.status == "pending").count(),
    }


def get_agent_next_action(db: Session) -> dict:
    """What the agent is doing / will do next — for Insights page."""
    from db.models import AgentStatus, FundManagerDecision
    from agent.signals import analyse_symbol

    status_row = db.query(AgentStatus).first()
    agent_status = status_row.status if status_row else "idle"
    interval = status_row.loop_interval if status_row else settings.agent_loop_interval
    last_run = status_row.last_run_at if status_row else None

    next_run_at = None
    seconds_until = None
    if last_run:
        next_run = last_run.replace(tzinfo=None) + timedelta(seconds=interval)
        seconds_until = max(0, int((next_run - datetime.utcnow()).total_seconds()))
        next_run_at = next_run.isoformat()

    pending = (
        db.query(AgentDecision)
        .filter(AgentDecision.status == "pending")
        .order_by(desc(AgentDecision.created_at))
        .all()
    )
    last_decision = db.query(AgentDecision).order_by(desc(AgentDecision.created_at)).first()
    fm = db.query(FundManagerDecision).order_by(desc(FundManagerDecision.created_at)).first()

    # Lightweight signal scan (no LLM cost)
    signal_rankings = []
    for coin in settings.watch_coin_list:
        try:
            signal_rankings.append(analyse_symbol(db, coin))
        except Exception:
            pass
    signal_rankings.sort(key=lambda x: abs(x.get("signal_score") or 0), reverse=True)
    top_signals = signal_rankings[:5]
    top = top_signals[0] if top_signals else None

    next_action = "scan"
    next_coin = None
    next_direction = None
    confidence = 0
    reasoning = []

    if agent_status in ("running", "analysing"):
        next_action = "executing"
        reasoning.append(f"Agent is {agent_status} — cycle in progress")
    elif pending:
        p = pending[0]
        next_action = "monitor"
        next_coin = p.coin
        next_direction = p.direction
        confidence = p.confidence or 0
        reasoning.append(
            f"Monitoring open {p.direction.upper()} {p.coin} — entry ${p.entry_price:.2f}, TP ${p.take_profit:.2f}, SL ${p.stop_loss:.2f}"
        )
    elif fm and fm.action in ("reserve", "hold"):
        next_action = "hold"
        reasoning.append(f"Fund Manager: {fm.action.upper()} — capital preserved")
    elif top and abs(top.get("signal_score") or 0) >= 35:
        score = top["signal_score"]
        next_direction = "long" if score > 0 else "short"
        next_action = "buy" if score > 0 else "sell"
        next_coin = top["symbol"]
        confidence = min(abs(score), 100)
        rsi = top.get("rsi")
        macd_trend = top.get("macd", {}).get("trend", "neutral")
        reasoning.append(
            f"Strongest signal: {next_coin} {next_direction.upper()} (score {score})"
        )
        reasoning.append(f"RSI {rsi:.0f}" if rsi else "RSI N/A")
        reasoning.append(f"MACD trend: {macd_trend}")
        if top.get("volume", {}).get("spike"):
            reasoning.append("Volume spike detected")
    else:
        reasoning.append("Scanning watchlist — waiting for confidence threshold on next cycle")

    if fm:
        reasoning.insert(0, f"Fund Manager: {fm.action.upper()} — {fm.reasoning[:120]}")

    # Prediction analysis narrative
    predictions = get_wealth_predictions(db)
    pred_text = (
        f"If avg daily P&L of ${predictions['avg_daily_pnl']:.2f} continues, "
        f"7-day outlook is ${predictions['projections'][0]['projected_pnl']:+.2f}. "
    )
    if next_action in ("buy", "sell") and next_coin:
        pred_text += (
            f"Next likely trade: {next_action.upper()} {next_coin} ({next_direction}) "
            f"at ~{confidence}% signal confidence when cycle runs."
        )
    elif next_action == "monitor" and pending:
        pred_text += f"Focus: manage existing {pending[0].coin} position until TP or SL hit."
    else:
        pred_text += "No high-confidence entry yet — agent will re-scan in next cycle."

    action_labels = {
        "buy": f"BUY {next_coin}",
        "sell": f"SELL {next_coin}",
        "monitor": f"MONITOR {next_coin}",
        "hold": "HOLD — preserve capital",
        "scan": "SCANNING markets",
        "executing": "RUNNING cycle",
    }

    return {
        "agent_status": agent_status,
        "next_run_at": next_run_at,
        "seconds_until_next_cycle": seconds_until,
        "next_action": next_action,
        "next_action_label": action_labels.get(next_action, next_action.upper()),
        "next_coin": next_coin,
        "next_direction": next_direction,
        "confidence": round(confidence, 1),
        "reasoning": reasoning,
        "prediction_analysis": pred_text,
        "fund_manager": {
            "action": fm.action if fm else None,
            "reasoning": fm.reasoning if fm else None,
            "target_daily_profit": round(fm.target_daily_profit, 2) if fm and fm.target_daily_profit else None,
        } if fm else None,
        "pending_trades": [
            {
                "coin": p.coin,
                "direction": p.direction,
                "entry_price": p.entry_price,
                "take_profit": p.take_profit,
                "stop_loss": p.stop_loss,
                "confidence": p.confidence,
            }
            for p in pending
        ],
        "top_signals": [
            {
                "symbol": s["symbol"],
                "signal_score": s.get("signal_score"),
                "rsi": s.get("rsi"),
                "macd_trend": s.get("macd", {}).get("trend"),
                "suggested": "long" if (s.get("signal_score") or 0) > 0 else "short",
            }
            for s in top_signals
        ],
        "last_decision": {
            "coin": last_decision.coin,
            "direction": last_decision.direction,
            "status": last_decision.status,
            "confidence": last_decision.confidence,
            "created_at": last_decision.created_at.isoformat() if last_decision and last_decision.created_at else None,
        } if last_decision else None,
    }


def get_full_insights(db: Session) -> dict:
    """Combined payload for Insights page."""
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "trading": get_trading_overview(db),
        "next_action": get_agent_next_action(db),
        "daily_pnl": get_daily_pnl(db),
        "wealth": get_wealth_growth(db),
        "predictions": get_wealth_predictions(db),
        "learnings": get_learnings(db),
    }
