# CryptoAgent — Project Scope & Agent Guide

This document gives a Cursor agent (or any developer) full context on **CryptoAgent**: an autonomous crypto trading system with live market data, multiple AI agents, paper/live trading, analytics, and zero-touch operations.

**Repo:** `https://github.com/BLSThathsara20/cryptoagent`  
**Stack:** Docker Compose · FastAPI (Python 3.11) · React 18 + Vite + Tailwind · PostgreSQL 15

---

## 1. What This Project Does

CryptoAgent is a **fully automatic** crypto trading platform:

1. **Ingests** market data (CoinGecko, Binance WebSocket, Coinglass, Fear & Greed).
2. **Runs agents** on a timer (default 5 min): Fund Manager → Trading Agent → execution.
3. **Trades** in **paper mode** by default; live Binance orders when enabled via UI or `.env`.
4. **Learns** from closed trades (memories fed back into LLM context).
5. **Monitors itself** via Autopilot + Validation Agent (health, accuracy, issues).
6. **Optimizes the DB** via retention jobs (auto-delete old/garbage data, VACUUM).

**User goal:** Set `.env` once, run `docker compose up -d`, minimal manual work.

---

## 2. Architecture

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────┐
│   Frontend   │────▶│     Backend     │────▶│  PostgreSQL  │
│ React :3000  │     │  FastAPI :8000  │     │   (internal) │
└──────────────┘     └────────┬────────┘     └──────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
    CoinGecko            Binance WS           Coinglass
    Fear&Greed           (order book)         (optional key)
```

### Containers (`docker-compose.yml`)

| Service | Port | Volume mount | Notes |
|---------|------|--------------|-------|
| `db` | internal only | `postgres_data` | No host 5432 (avoids conflicts) |
| `backend` | 8000 | `./backend:/app`, `./backups:/backups` | Hot reload via uvicorn |
| `frontend` | 3000 | `./frontend:/app` | Vite dev; `/api` proxied to backend |

**After `.env` changes:** `docker compose up -d --force-recreate backend`

---

## 3. Frontend Pages & Routes

| Route | Page | Purpose |
|-------|------|---------|
| `/` | `Dashboard.jsx` | Market data: prices, charts, order book, liquidations |
| `/agent` | `Agent.jsx` | Fund Manager, LLM usage, trading agent panel, trade history |
| `/insights` | `Insights.jsx` | P&L, wealth growth, projections, learning, **next agent action** |
| `/issues` | `Issues.jsx` | Validation Agent results, health score, open issues |
| `/settings` | `Settings.jsx` | System health, autopilot tasks, pipeline, capabilities |

**Key components:** `LiveTradingToggle`, `LLMUsagePanel`, `AlertBell`, `IssuesNavLink` (badge count).

**Charts:** `lightweight-charts` (candles), `recharts` (Insights analytics).

**API helper:** `frontend/src/api.js` — `fetchAPI`, `postAPI`, `putAPI` → `/api/*`.

---

## 4. Backend Agents (Autonomous)

All agents run automatically; no manual trigger required (optional `POST /api/agent/run-cycle`).

### 4.1 Fund Manager Agent
- **File:** `backend/agent/fund_manager.py`
- **Role:** Capital allocation, reserve %, deployable balance, portfolio snapshots.
- **Writes:** `portfolio_snapshots`, `fund_manager_decisions`
- **Runs:** Start of every agent cycle.

### 4.2 Trading Agent (AI Brain)
- **Files:** `loop.py`, `analyser.py`, `brain.py`, `signals.py`, `executor.py`
- **Cycle:** analyse → backtest → score → LLM/rule decision → execute → log
- **LLM:** OpenAI (default) or Claude; budget cap via `LLM_MONTHLY_BUDGET_USD`
- **Fallback:** Rule-based signals when budget exceeded or no API key
- **Writes:** `agent_decisions`, `paper_account`, `paper_pnl_history`, `agent_memories`

### 4.3 Validation Agent
- **File:** `backend/agent/validator.py`
- **Schedule:** Every 15 min + on startup
- **Checks:** DB, WebSocket, data freshness, Binance, OpenAI, agent loop, drawdown, win rate, live mode config
- **Writes:** `validation_runs`, `system_issues` (deleted when fixed/dismissed)

### 4.4 Autopilot
- **File:** `backend/autopilot/scheduler.py`
- **Schedule:** Every 15 min
- **Role:** DB size warnings, WS disconnect notes, stuck agent recovery

### 4.5 Background Schedulers (in `main.py` lifespan)

| Scheduler | Interval | Module |
|-----------|----------|--------|
| Data ingestion | 60s | `data/ingestion.py` |
| Data retention + VACUUM | daily 03:00 + every 6h | `data/retention.py` |
| Auto backup (pg_dump) | daily 02:00 | `data/backup.py` |
| Autopilot health | 15 min | `autopilot/scheduler.py` |
| Validation Agent | 15 min | `agent/validator.py` |
| Agent trading loop | `AGENT_LOOP_INTERVAL` (300s) | `agent/loop.py` |
| Binance WebSocket | continuous | `data/binance_ws.py` |

---

## 5. Database Models (`backend/db/models.py`)

| Table | Purpose |
|-------|---------|
| `coin_prices`, `market_dominance`, `order_book`, `live_trades` | Market data |
| `liquidations`, `long_short_ratios`, `fear_greed_index` | Sentiment / derivatives |
| `agent_decisions` | Trades (pending/win/loss/cancelled) |
| `paper_account`, `paper_pnl_history` | Mock trading balance |
| `agent_status` | Runtime config incl. `live_mode` |
| `agent_memories` | Lessons from closed trades (capped at 200) |
| `portfolio_snapshots` | Wealth over time |
| `fund_manager_decisions` | Capital actions |
| `system_alerts` | Notifications (**deleted on read**) |
| `llm_usage_logs`, `llm_monthly_spend` | AI cost tracking (4 months history) |
| `system_issues` | Validation issues (**deleted on dismiss**) |
| `validation_runs` | Health check history (keep last 30) |

**Init:** `db/session.py` → `init_db()` creates tables + indexes on startup.

---

## 6. API Endpoints (prefix `/api`)

### Market — `/api/market`
`prices`, `dominance`, `fear-greed`, `orderbook/{symbol}`, `trades/{symbol}`, `liquidations`, `long-short`, `candles/{symbol}`

### Agent — `/api/agent`
`status`, `last-decision`, `paper-account`, `pnl-history`, `PUT settings`, `POST run-cycle`

### Trades — `/api/trades`
`history`, `stats`

### Portfolio — `/api/portfolio`
`holdings`, `fund-manager/latest`, `fund-manager/history`, `POST fund-manager/run`, `snapshots`

### Analytics — `/api/analytics`
`overview`, `daily-pnl`, `wealth`, `predictions`, `learnings`, `next-action`, `trading`

### Issues — `/api/issues`
`GET` (summary), `POST validate`, `POST {id}/resolve` (deletes issue)

### Alerts — `/api/alerts`
`GET`, `unread-count`, `POST {id}/read` (**deletes**), `POST read-all` (**deletes all**), `POST test-binance`

### LLM — `/api/llm`
`usage`, `POST test`

### System — `/api/system`
`status`, `memories`

**Health:** `GET /health`

---

## 7. Configuration (`.env`)

Copy from `.env.example`. **Never commit `.env`.**

| Variable | Meaning |
|----------|---------|
| `LLM_PROVIDER` | `openai` or `claude` |
| `OPENAI_API_KEY` / `CLAUDE_API_KEY` | AI brain |
| `LLM_MONTHLY_BUDGET_USD` | Hard cap; fallback to rules when exceeded |
| `LIVE_MODE` | Initial live flag; **UI toggle overrides at runtime** |
| `BINANCE_API_KEY/SECRET` | Balances + live orders (Reading permission minimum) |
| `AGENT_LOOP_INTERVAL` | Seconds between trading cycles (default 300) |
| `FUND_RESERVE_PERCENT` | % kept in reserve |
| `RETAIN_*_DAYS` | Data retention windows |
| `AUTO_BACKUP_ENABLED` | Daily pg_dump to `./backups` |

**Live trading:** Can enable via Insights/Agent UI (`PUT /api/agent/settings`) without editing `.env`.

---

## 8. Data Retention & DB Optimization

**File:** `backend/data/retention.py`

Automatically deletes:
- Old order book, live trades, coin prices, market meta (per `RETAIN_*`)
- Read alerts immediately; stale unread after 30 days
- LLM logs > 60 days; monthly spend > 4 months
- Validation runs > 30; fund manager decisions > 60 days
- Cancelled trades > 14 days; agent memories > 200 newest
- Resolved issues > 1 day

Runs `VACUUM ANALYZE` after cleanup.

---

## 9. Key File Map

```
cryptoagent/
├── docker-compose.yml
├── .env.example          # Template only
├── AGENTS.md             # This file
├── README.md             # User-facing setup guide
├── backend/
│   ├── main.py           # FastAPI app, lifespan, router registration
│   ├── config.py         # Settings from env
│   ├── agent/
│   │   ├── loop.py       # Main trading cycle
│   │   ├── fund_manager.py
│   │   ├── analyser.py   # Market context builder
│   │   ├── brain.py      # LLM + validation
│   │   ├── signals.py    # RSI, MACD, volume
│   │   ├── executor.py   # Paper/live execution, P&L close, memories
│   │   ├── llm_usage.py  # Token/cost tracking
│   │   └── validator.py  # Validation Agent
│   ├── analytics/
│   │   └── insights.py   # P&L, wealth, predictions, next action
│   ├── data/             # Ingestion, WS, retention, backup
│   ├── alerts/           # Alert create/delete
│   ├── autopilot/        # Health scheduler
│   ├── db/               # models.py, session.py
│   └── routers/          # FastAPI routes
└── frontend/
    └── src/
        ├── App.jsx       # Routes + nav
        ├── api.js
        ├── pages/        # Dashboard, Agent, Insights, Issues, Settings
        └── components/   # Reusable UI widgets
```

---

## 10. Development Conventions

- **Paper mode is default.** Live mode requires explicit UI confirmation.
- **Minimize scope** when editing — match existing patterns (Tailwind `.card`, polling intervals).
- **Alerts:** Delete on read, don't accumulate.
- **Issues:** Delete on dismiss; validator auto-deletes when check passes.
- **LLM usage:** Don't call OpenAI on every poll; use cached status in `get_usage_summary`.
- **Agent cycle errors:** Check `docker logs cryptoagent-backend`; common fix: SQL in `analyser._latest_prices` uses `func.max(timestamp)`.
- **Binance -2015:** API key IP whitelist or missing Reading permission.

### Common Commands

```bash
docker compose up -d --build          # Start all
docker compose logs -f backend      # Debug
docker compose restart backend      # Reload code (volume mounted)
docker compose up -d --force-recreate backend  # Reload .env
```

### Testing APIs

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/analytics/overview
curl http://localhost:8000/api/issues
curl http://localhost:8000/api/llm/usage
```

---

## 11. Feature Status (as of Jul 2026)

| Feature | Status |
|---------|--------|
| Market dashboard | ✅ Complete |
| Paper trading | ✅ Complete |
| Live trading (Binance) | ✅ Orders placed; P&L close still paper-style |
| Fund Manager agent | ✅ Complete |
| LLM usage + budget | ✅ Complete |
| Insights page (P&L, wealth, learning) | ✅ Complete |
| Agent next-action preview | ✅ Complete |
| Validation Agent + Issues page | ✅ Complete |
| Live/mock toggle in UI | ✅ Complete |
| Auto DB cleanup | ✅ Complete |
| Multi-provider Gemini | ❌ Planned |

---

## 12. What NOT to Do

- Do **not** commit `.env`, API keys, or `backups/*.sql`.
- Do **not** force-push `main`.
- Do **not** expose PostgreSQL port unless needed (security).
- Do **not** enable live trading without Binance keys + user confirmation.

---

## 13. Extending the Project

**Add a new API route:** Create router in `backend/routers/`, register in `main.py`.

**Add a new page:** Create `frontend/src/pages/X.jsx`, add route in `App.jsx`, add nav link.

**Add a new scheduled job:** Use APScheduler pattern from `data/retention.py` or `agent/validator.py`, start in `main.py` lifespan.

**Add analytics:** Extend `backend/analytics/insights.py`, expose via `routers/analytics.py`, consume in `Insights.jsx`.
