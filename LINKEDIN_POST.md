# LinkedIn Post — CryptoAgent

**Repo:** https://github.com/BLSThathsara20/cryptoagent  
**Language level:** B1 English (clear and simple)  
**How to use:** Pick 1 title → copy the post body → paste on LinkedIn. Add 1–2 screenshots if you can.

---

## 10 Title Options (pick one)

1. I Built an AI Crypto Trading System That Works While I Sleep  
2. From Idea to Live Agents: My Autonomous Crypto Trading Project  
3. What If Your Trading Bot Could Learn From Every Win and Loss?  
4. I Built CryptoAgent — Multi-Agent AI for Paper and Live Trading  
5. Why I Built a Self-Monitoring Crypto Trading Platform With AI Agents  
6. No More Manual Charts All Night — I Automated My Crypto Research  
7. Building With AI Agents: Fund Manager, Trader, Validator in One App  
8. My Open Project: Autonomous Crypto Trading With Docker and React  
9. How Multiple AI Agents Work Together in My Crypto Trading System  
10. I Wanted a Trading System I Can Trust — So I Built CryptoAgent  

**Recommended for LinkedIn:** Title **1** or **5** (clear story + strong hook).

---

## Full LinkedIn Post (copy below)

### Suggested title (use as first line / hook)

**I Built an AI Crypto Trading System That Works While I Sleep**

---

A few months ago I had a simple problem.

I like crypto. I also like sleep.  
I did not want to watch charts all night.  
And I did not want a “blind” bot that trades without learning.

So I built **CryptoAgent**.

### Why I built it

I wanted a system that can:

- collect market data automatically  
- think before it trades  
- start in **paper mode** (safe, no real money first)  
- learn from every closed trade  
- check its own health when something breaks  
- restart itself after the internet comes back  

In short: less panic, more process.

### What is CryptoAgent?

CryptoAgent is an **autonomous crypto trading platform**.

You set your config once, start it with Docker, and the agents keep working.

Stack (for the builders here):

- React dashboard  
- FastAPI backend  
- PostgreSQL  
- Docker Compose  
- Live data from CoinGecko, Binance WebSocket, Fear & Greed, and more  

### The agents (this is the cool part)

I did not build one big “magic AI”.  
I built a **team of agents**, each with one job.

1. **Fund Manager Agent**  
   Looks at capital, reserve, and risk. Decides how much money is safe to use.

2. **Trading Agent (AI brain)**  
   Reads the market, checks technical signals, and decides long / short / wait.  
   It can use OpenAI (or rules when budget is low).  
   Default mode is **paper trading**. Live Binance trading is optional and must be turned on with care.

3. **Validation Agent**  
   Checks the system every few minutes: database, WebSocket, data freshness, API health, win rate, and more.  
   Problems show on an **Issues** page — like a health report for the whole system.

4. **Autopilot / Recovery**  
   If the network drops and comes back, services try to restart.  
   The agent loop can also restart automatically (and there is a manual restart button if needed).

5. **Learning layer**  
   When a trade closes (win or loss), the system stores a lesson.  
   Those lessons come back into later decisions.  
   There is also a small local model that updates over time from real outcomes.

### How a normal cycle works

Every few minutes:

1. Collect / refresh market data  
2. Fund Manager checks capital  
3. Trading Agent analyses and decides  
4. Execute (paper or live)  
5. Later: close trade → learn → update stats  

You can watch everything live:

- Dashboard (prices, order book, charts)  
- Agent page (status, trades, settings)  
- Insights (P&L, learning, next action)  
- Learning Hub (today’s P&L + lessons)  
- Issues (system health)  

### Why use agents like this?

Because trading is not only “buy” and “sell”.

You also need:

- risk control  
- data quality  
- cost control (AI budget)  
- recovery after offline  
- memory from past mistakes  

One script cannot do all of that well.  
A small team of agents can.

### What I learned while building this

- Paper mode first is not optional. It is survival.  
- Live UI updates matter. People trust what they can see.  
- Self-checks save hours of debugging.  
- After offline, auto-restart is as important as the trading logic.  
- Learning only helps when you learn from **closed** trades, not from hope.

### Who is this for?

- Developers who want a real multi-agent project  
- Traders who want automation with visibility  
- Students who want to learn FastAPI + React + Docker + AI in one system  

### Important note

This is still a project for learning and careful use.  
Crypto is risky. Start with paper mode. Never trade money you cannot lose.

### Open source

If you want to explore the code:

**GitHub:** https://github.com/BLSThathsara20/cryptoagent

I am happy to connect with people building AI agents, trading systems, or full-stack automation.

What would you automate first if you had a team of agents working for you?

---

#Crypto #AI #Agents #FinTech #OpenSource #Docker #FastAPI #React #BuildInPublic #TradingBots

---

## Short version (if LinkedIn character limit / you want a shorter post)

**I Built an AI Crypto Trading System That Works While I Sleep**

I built **CryptoAgent** because I wanted crypto automation without watching charts all night.

It runs with Docker and uses several agents:

- Fund Manager (risk & capital)  
- Trading Agent (decides trades, paper first)  
- Validation Agent (checks system health)  
- Learning (remembers wins and losses)  
- Autopilot (restarts after offline)

You can see live prices, P&L, lessons, and issues in a React dashboard.

Start in paper mode. Learn first. Then decide.

GitHub: https://github.com/BLSThathsara20/cryptoagent

#AI #Crypto #Agents #BuildInPublic #OpenSource

---

## Posting tips

1. Use **Title 1 or 5** as the first bold line.  
2. Add 1 screenshot of Dashboard + 1 of Issues/Learning.  
3. End with a question (people comment more).  
4. Keep B1 English — short sentences, clear words.  
5. Do not promise profits. Say “paper mode first” and “crypto is risky”.
