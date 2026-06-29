# CryptoAgent

Autonomous crypto trading AI agent with a live market data dashboard and Claude-powered decision engine. Fully containerized with Docker Compose for deployment on local machines, VPS, DigitalOcean, or Hetzner.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌────────────┐
│  Frontend   │────▶│   Backend    │────▶│ PostgreSQL │
│ React+Vite  │     │   FastAPI    │     │     15     │
│  Port 3000  │     │  Port 8000   │     │  Port 5432 │
└─────────────┘     └──────────────┘     └────────────┘
                           │
                    ┌──────┴──────┐
                    │  Data APIs  │
                    │ CoinGecko   │
                    │ Binance WS  │
                    │ Coinglass   │
                    │ Fear&Greed  │
                    └─────────────┘
```

Three Docker containers:
- **backend** — Python FastAPI (data ingestion, AI agent, trading logic)
- **frontend** — React + Tailwind (live dashboard)
- **db** — PostgreSQL (market data, trades, agent decisions)

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Claude API key (for AI decisions)

### Setup

1. Clone the repository:
   ```bash
   git clone <repo-url> cryptoagent
   cd cryptoagent
   ```

2. Create your environment file:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` and set at minimum:
   ```
   POSTGRES_PASSWORD=your_secure_password
   CLAUDE_API_KEY=sk-ant-...
   ```

4. Start everything:
   ```bash
   docker-compose up --build
   ```

5. Open the dashboard:
   - **Dashboard**: http://localhost:3000
   - **API docs**: http://localhost:8000/docs
   - **Health check**: http://localhost:8000/health

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_USER` | Database username | `cryptoagent` |
| `POSTGRES_PASSWORD` | Database password | — |
| `POSTGRES_DB` | Database name | `cryptoagent` |
| `CLAUDE_API_KEY` | Anthropic API key for AI agent | — |
| `BINANCE_API_KEY` | Binance API key (live trading) | — |
| `BINANCE_SECRET` | Binance API secret (live trading) | — |
| `COINGLASS_API_KEY` | Coinglass API key (optional) | — |
| `LIVE_MODE` | Enable real trading (`true`/`false`) | `false` |
| `STARTING_BALANCE` | Paper trading starting balance | `10000` |
| `AGENT_LOOP_INTERVAL` | Agent cycle interval in seconds | `300` |
| `MAX_RISK_PERCENT` | Max risk per trade (% of balance) | `2` |
| `WATCH_COINS` | Comma-separated coins to watch | `BTC,ETH,SOL,...` |

## Features

### Layer 1 — Live Market Data
- Top 50 coin prices from CoinGecko (every 60s)
- Real-time order book and trades via Binance WebSocket
- Liquidations and long/short ratios from Coinglass
- Fear & Greed Index from Alternative.me
- BTC/ETH dominance tracking

### Layer 2 — AI Trading Agent
The agent runs on a continuous loop (default: every 5 minutes):

1. **Analyse** — reads latest market data, identifies patterns
2. **Backtest** — tests setups against 30 days of stored data
3. **Score** — ranks opportunities with confidence (0–100)
4. **Decide** — selects best trade with entry, TP, SL, position size
5. **Execute** — paper trading by default; live when enabled
6. **Log** — records every decision and outcome

Technical signals (RSI, MACD, volume spikes) are combined with Claude AI reasoning.

### Dashboard
- Live price ticker for top 20 coins
- Candlestick charts (TradingView lightweight-charts)
- Order book visualizer (bids green, asks red)
- Live trade feed
- Liquidation table
- Long/short ratio bars
- BTC dominance gauge
- Fear & Greed Index
- Sortable market overview table

### Agent Panel
- Agent status indicator
- Last decision card with reasoning
- Trade history with win/loss outcomes
- Paper trading P&L chart
- Paper/Live mode toggle (with confirmation)
- Configurable loop interval, risk %, watch coins

## Switching to Live Trading

> **Warning**: Live trading uses real money. Only enable after thorough paper trading validation.

1. Set Binance API credentials in `.env`:
   ```
   BINANCE_API_KEY=your_key
   BINANCE_SECRET=your_secret
   ```

2. Ensure API key has spot trading permissions (not withdrawal).

3. Enable live mode either via:
   - `.env`: `LIVE_MODE=true` (requires container restart)
   - Dashboard: Agent page → toggle to LIVE (with confirmation dialog)

4. Risk management is enforced:
   - Max 2% of balance per trade (configurable)
   - Stop loss is mandatory on every trade
   - Agent rejects trades without a defined stop loss

## Deployment (VPS / Cloud)

Works on any Docker-capable host:

```bash
# On your VPS (DigitalOcean, Hetzner, etc.)
git clone <repo-url> cryptoagent && cd cryptoagent
cp .env.example .env
nano .env  # configure credentials
docker-compose up -d --build
```

Use a reverse proxy (nginx/Caddy) for HTTPS in production:

```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com;

    location / {
        proxy_pass http://localhost:3000;
    }
    location /api {
        proxy_pass http://localhost:8000;
    }
}
```

## Project Structure

```
cryptoagent/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── agent/          # AI trading agent
│   ├── data/           # Market data ingestion
│   ├── db/             # SQLAlchemy models
│   └── routers/        # API endpoints
└── frontend/
    └── src/
        ├── components/  # Dashboard widgets
        └── pages/         # Dashboard & Agent views
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/market/prices` | Top coin prices |
| `GET /api/market/dominance` | BTC/ETH dominance |
| `GET /api/market/fear-greed` | Fear & Greed Index |
| `GET /api/market/orderbook/{symbol}` | Order book |
| `GET /api/market/trades/{symbol}` | Live trades |
| `GET /api/market/liquidations` | Liquidations |
| `GET /api/market/long-short` | Long/short ratios |
| `GET /api/market/candles/{symbol}` | Chart data |
| `GET /api/agent/status` | Agent status |
| `GET /api/agent/last-decision` | Latest decision |
| `GET /api/agent/paper-account` | Paper account stats |
| `GET /api/trades/history` | Trade history |
| `PUT /api/agent/settings` | Update agent config |

## License

MIT
