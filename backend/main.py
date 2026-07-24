"""CryptoAgent FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db.session import init_db
from data.ingestion import start_ingestion_scheduler, stop_ingestion_scheduler, run_all_fetchers
from data.retention import start_maintenance_scheduler, stop_maintenance_scheduler
from data.backup import start_backup_scheduler, stop_backup_scheduler, run_auto_backup
from autopilot.scheduler import start_autopilot_scheduler, stop_autopilot_scheduler
from data.binance_ws import binance_ws_loop, stop_binance_ws
from agent.loop import start_agent_loop, stop_agent_loop
from agent.validator import start_validation_scheduler, stop_validation_scheduler, run_validation
from routers import market, agent, trades, system, portfolio, alerts, llm, analytics, issues

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    logger.info("CryptoAgent starting up...")
    init_db()

    # Start background services
    start_ingestion_scheduler()
    start_maintenance_scheduler()
    start_backup_scheduler()
    start_autopilot_scheduler()
    start_validation_scheduler()
    asyncio.create_task(binance_ws_loop())
    start_agent_loop()

    # Run initial data fetch + first backup after startup
    await run_all_fetchers()
    run_auto_backup()

    # Test Binance + welcome alert
    from db.session import SessionLocal
    from alerts.manager import create_alert
    from agent.binance_client import is_configured, fetch_spot_balances
    db = SessionLocal()
    try:
        if is_configured():
            bal = fetch_spot_balances()
            if bal:
                create_alert(
                    db, "success", "binance", "Binance API Connected",
                    f"Reading {len(bal)} assets from your account. "
                    f"Trading mode: {'LIVE' if settings.live_mode else 'PAPER (mock trades only)'}.",
                )
            else:
                create_alert(
                    db, "error", "binance", "Binance Connection Failed",
                    "Keys found but connection failed. Check permissions (Enable Reading) and IP whitelist.",
                )
        create_alert(
            db, "success", "system", "Autopilot Active",
            f"All agents running automatically. Mode: {'LIVE' if settings.live_mode else 'PAPER'}. "
            f"No manual steps needed — data, trades, cleanup, and backups are handled for you.",
        )
    finally:
        db.close()

    # Initial validation run
    db = SessionLocal()
    try:
        run_validation(db)
    except Exception as e:
        logger.warning("Initial validation run failed: %s", e)
    finally:
        db.close()

    logger.info("CryptoAgent ready")
    yield

    # Shutdown
    logger.info("CryptoAgent shutting down...")
    stop_ingestion_scheduler()
    stop_maintenance_scheduler()
    stop_backup_scheduler()
    stop_autopilot_scheduler()
    stop_validation_scheduler()
    stop_binance_ws()
    stop_agent_loop()


app = FastAPI(
    title="CryptoAgent",
    description="Autonomous crypto trading AI agent system",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router)
app.include_router(agent.router)
app.include_router(trades.router)
app.include_router(system.router)
app.include_router(portfolio.router)
app.include_router(alerts.router)
app.include_router(llm.router)
app.include_router(analytics.router)
app.include_router(issues.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "CryptoAgent"}
