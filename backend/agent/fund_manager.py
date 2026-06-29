"""Fund Manager Agent — reads balances, analyzes allocation, manages capital."""

import logging
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import desc

from config import settings
from db.models import (
    PortfolioSnapshot,
    FundManagerDecision,
    PaperAccount,
    AgentDecision,
    CoinPrice,
)
from agent.binance_client import (
    fetch_spot_balances,
    get_usd_prices,
    is_configured,
    STABLECOINS,
)

logger = logging.getLogger(__name__)


def _get_price_from_db(db: Session, symbol: str) -> float:
    row = (
        db.query(CoinPrice)
        .filter(CoinPrice.symbol == symbol.upper())
        .order_by(desc(CoinPrice.timestamp))
        .first()
    )
    return float(row.price) if row else 0.0


def _build_paper_portfolio(db: Session) -> dict:
    """Simulate portfolio from paper account + open trades."""
    account = db.query(PaperAccount).first()
    balance = account.balance if account else settings.starting_balance

    pending = db.query(AgentDecision).filter(AgentDecision.status == "pending").all()
    deployed = 0.0
    holdings = []

    for trade in pending:
        risk = abs(trade.entry_price - trade.stop_loss)
        size = (balance * settings.max_risk_percent / 100) / risk if risk > 0 else 0
        usd_value = size * trade.entry_price
        deployed += usd_value
        holdings.append(
            {
                "asset": trade.coin,
                "amount": size,
                "usd_value": round(usd_value, 2),
                "percent": 0,
                "type": "open_trade",
                "direction": trade.direction,
            }
        )

    available = max(0, balance - deployed)
    stable_usd = available
    crypto_usd = deployed
    total = balance

    holdings.insert(
        0,
        {
            "asset": "USDT",
            "amount": available,
            "usd_value": round(available, 2),
            "percent": 0,
            "type": "stable",
        },
    )

    for h in holdings:
        h["percent"] = round((h["usd_value"] / total * 100) if total > 0 else 0, 2)

    return {
        "source": "paper",
        "total_usd": round(total, 2),
        "stable_usd": round(stable_usd, 2),
        "crypto_usd": round(crypto_usd, 2),
        "deployed_usd": round(deployed, 2),
        "available_usd": round(available, 2),
        "holdings": holdings,
    }


def _build_binance_portfolio(db: Session) -> dict | None:
    """Build portfolio from live Binance spot balances."""
    balances = fetch_spot_balances()
    if balances is None:
        return None

    assets = list(balances.keys())
    prices = get_usd_prices(assets)

    # Fill missing prices from DB
    for asset in assets:
        if asset not in STABLECOINS and prices.get(asset, 0) <= 0:
            prices[asset] = _get_price_from_db(db, asset)

    holdings = []
    stable_usd = crypto_usd = 0.0

    for asset, bal in balances.items():
        usd_value = bal["total"] * prices.get(asset, 0)
        if usd_value < 0.01:
            continue
        is_stable = asset in STABLECOINS
        if is_stable:
            stable_usd += usd_value
        else:
            crypto_usd += usd_value
        holdings.append(
            {
                "asset": asset,
                "amount": bal["total"],
                "free": bal["free"],
                "used": bal["used"],
                "usd_value": round(usd_value, 2),
                "percent": 0,
                "type": "stable" if is_stable else "crypto",
            }
        )

    total = stable_usd + crypto_usd
    for h in holdings:
        h["percent"] = round((h["usd_value"] / total * 100) if total > 0 else 0, 2)

    holdings.sort(key=lambda x: x["usd_value"], reverse=True)

    pending = db.query(AgentDecision).filter(AgentDecision.status == "pending").count()
    deployed_estimate = crypto_usd * 0.5 if pending else 0  # rough estimate

    return {
        "source": "binance",
        "total_usd": round(total, 2),
        "stable_usd": round(stable_usd, 2),
        "crypto_usd": round(crypto_usd, 2),
        "deployed_usd": round(deployed_estimate, 2),
        "available_usd": round(stable_usd, 2),
        "holdings": holdings,
    }


def get_portfolio(db: Session) -> dict:
    """Get current portfolio — reads Binance if keys set, trades stay paper unless LIVE_MODE."""
    if is_configured():
        live = _build_binance_portfolio(db)
        if live:
            live["trading_mode"] = "live" if settings.live_mode else "paper"
            return live
    paper = _build_paper_portfolio(db)
    paper["trading_mode"] = "paper"
    return paper


def _save_snapshot(db: Session, portfolio: dict) -> PortfolioSnapshot:
    snap = PortfolioSnapshot(
        source=portfolio["source"],
        total_usd=portfolio["total_usd"],
        stable_usd=portfolio["stable_usd"],
        crypto_usd=portfolio["crypto_usd"],
        deployed_usd=portfolio["deployed_usd"],
        available_usd=portfolio["available_usd"],
        holdings=portfolio["holdings"],
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def analyze_and_manage(db: Session) -> FundManagerDecision:
    """
    Fund Manager Agent core logic:
    - See where funds are
    - Check reserve vs deployable capital
    - Check concentration limits
    - Recommend actions toward daily profit target
    """
    portfolio = get_portfolio(db)
    _save_snapshot(db, portfolio)

    total = portfolio["total_usd"]
    reserve_pct = settings.fund_reserve_percent
    max_coin_pct = settings.max_allocation_per_coin
    daily_target = total * (settings.daily_profit_target_percent / 100)

    min_reserve = total * (reserve_pct / 100)
    max_deploy = total - min_reserve
    stable = portfolio["stable_usd"]
    available = portfolio["available_usd"]

    actions = []
    action = "hold"
    asset = None
    amount_usd = 0.0

    # Rule 1: Not enough stable reserve
    if stable < min_reserve and portfolio["source"] == "binance":
        deficit = min_reserve - stable
        actions.append(f"Reserve below {reserve_pct}% target — need ${deficit:.0f} more in stables")
        action = "reserve"
        amount_usd = deficit
        reasoning = (
            f"Portfolio ${total:,.2f}: only {stable/total*100:.1f}% in stables "
            f"(target {reserve_pct}%). Recommend keeping ${min_reserve:,.0f} in USDT as safety buffer. "
            f"Daily profit target: ${daily_target:.2f} ({settings.daily_profit_target_percent}%)."
        )

    # Rule 2: Over-concentrated in one coin
    for h in portfolio["holdings"]:
        if h["type"] == "crypto" and h["percent"] > max_coin_pct:
            actions.append(f"{h['asset']} is {h['percent']}% — exceeds {max_coin_pct}% limit")
            if action == "hold":
                action = "reduce"
                asset = h["asset"]
                amount_usd = h["usd_value"] - (total * max_coin_pct / 100)
                reasoning = (
                    f"Over-concentrated in {h['asset']} ({h['percent']}% of portfolio). "
                    f"Reduce by ~${amount_usd:.0f} to limit risk. "
                    f"Goal: earn ${daily_target:.2f}/day without excessive exposure."
                )

    # Rule 3: Too much idle capital — ready to deploy for trading agent
    deployable = available - min_reserve
    if deployable > total * 0.05 and action == "hold":
        action = "deploy"
        amount_usd = min(deployable, max_deploy * settings.max_risk_percent / 100 * 5)
        asset = "USDT"
        reasoning = (
            f"Portfolio ${total:,.2f}: ${deployable:,.0f} deployable after {reserve_pct}% reserve. "
            f"Trading agent can use up to {settings.max_risk_percent}% per trade (${total * settings.max_risk_percent / 100:.0f} risk). "
            f"Daily target: ${daily_target:.2f}. Capital ready for next opportunity."
        )

    # Rule 4: Default hold with summary
    if action == "hold":
        reasoning = (
            f"Portfolio ${total:,.2f} ({portfolio['source']} mode): "
            f"{stable/total*100:.1f}% stables, {portfolio['crypto_usd']/total*100:.1f}% crypto, "
            f"${available:,.0f} available. Reserve target {reserve_pct}% met. "
            f"Daily profit target ${daily_target:.2f}. Holding — waiting for trading agent signal."
        )

    if len(actions) > 1:
        reasoning += " Issues: " + "; ".join(actions)

    decision = FundManagerDecision(
        action=action,
        asset=asset,
        amount_usd=round(amount_usd, 2) if amount_usd else None,
        reasoning=reasoning,
        portfolio_total=total,
        target_daily_profit=round(daily_target, 2),
        status="recommended",
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)

    logger.info("Fund Manager: %s — %s", action, reasoning[:100])
    return decision


def run_fund_manager_cycle(db: Session) -> dict:
    """Run fund manager and return portfolio + latest decision."""
    portfolio = get_portfolio(db)
    decision = analyze_and_manage(db)
    return {
        "portfolio": portfolio,
        "decision": {
            "id": decision.id,
            "action": decision.action,
            "asset": decision.asset,
            "amount_usd": decision.amount_usd,
            "reasoning": decision.reasoning,
            "portfolio_total": decision.portfolio_total,
            "target_daily_profit": decision.target_daily_profit,
            "status": decision.status,
            "created_at": decision.created_at.isoformat() if decision.created_at else None,
        },
    }
