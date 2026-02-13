# AI Advisor Bot

Semi-autonomous options analytics engine: **Phase 0–6** and **Phase 8** (excluding Phase 7 GCP). See **PROJECT_CONTEXT.md** for the full spec and backlog.

## Features (by phase)

- **Phase 0**: Docker Compose stack (API, Frontend, Postgres, Redis), DB schema (MarketData, TradeRecommendations, ActivePositions, AlertLog), FastAPI health check.
- **Phase 1**: Ingestion (Price, SMA_50, RSI_14, ATR_14, IV_30d), option chain (30–45 DTE), strategy selector, strike selection by delta, LLM thesis stub, market regime filter (SPY 200 SMA), expected move engine, **Frontend Approval Queue** (PENDING → Approve/Reject).
- **Phase 2**: **Portfolio state** (ActivePosition), **Watchman** (21 DTE, stop loss, take profit, data freshness), alert idempotency, heartbeat; **Frontend Watchtower** (active positions).
- **Phase 3**: S&P 500 universe loader, liquidity filter, **batch analysis** runner, earnings filter, sector correlation cap, rate limit controller.
- **Spec Patch v1.1**: IV/NATR formula with `sqrt(252)` and gate > 1.0; liquidity ADV > 5M and option spread < 10%; hard earnings exclusion (NO_TRADE); ticker-level trend filter (block Short Put if Price < SMA_50); **THESIS STALE** warning in Approval Queue; Watchman every **15 min** during market hours; **rolling lineage** on ActivePosition; **MarketDataProvider** abstraction; decimal precision audit (DECIMAL(10,4)+).
- **Phase 4 (Macro & Manager)**: **Macro calendar** gate (block new entries before high-impact events); **externalized config** (all thresholds in `config.Settings`); **refined entry gates** (RSI &lt; 40, annualized yield &gt; 20%); **Income Shield** (`ROLL_NEEDED` when ITM and DTE &lt; 14); **sector value exposure** (capital_deployed, max 70% per sector).
- **Phase 5 (Local Dev & Debugging)**: **APScheduler** for Watchman (no zombie loop); **DataFetchError** (no silent mock fallbacks); **Bid/Ask** (bid = credit, ask = buy-to-close); **recommendation idempotency** (return existing PENDING); **Decimal JSON** (serialize as strings).
- **Phase 6 (Institutional Mechanics)**: **Term structure** (IV/NATR at target expiry); **25Δ skew gate** (block Short Put if skew &gt; threshold).
- **Phase 8 (UI/UX Command Center)**: **Dark mode** (Slate-950/Zinc); **sidebar** (Dashboard, Analyst, Queue, Watchtower); **monospace** for financial data; **/analyst** (manual ticker analysis, result card, Open in Queue / Dismiss); **Dashboard /** (heartbeat, quick stats, batch trigger); **enhanced tables** (badges, expandable rows, copy contract ID); **toasts** (sonner) for Approve/Reject/Analysis/Batch.

## Run the stack (Docker)

```bash
# From repo root
docker compose up -d

# API
open http://localhost:8000
# Docs: http://localhost:8000/docs

# Frontend (Next.js) — Command Center (dark mode)
open http://localhost:3000
# Dashboard:     http://localhost:3000/
# Analyst:       http://localhost:3000/analyst
# Approval Queue: http://localhost:3000/approval-queue
# Watchtower:    http://localhost:3000/watchtower
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | DB status, mock_ingestion flag |
| POST | `/analyze/{ticker}` | Run analysis; returns §6.1 recommendation, persists as PENDING. Idempotent: returns existing PENDING if same ticker/strategy/expiry. Macro & sector gates applied. |
| GET | `/recommendations?status=PENDING` | List recommendations (Approval Queue) |
| POST | `/recommendations/{id}/approve` | Approve → create ActivePosition (with capital_deployed, sector), move to Monitor |
| POST | `/recommendations/{id}/reject` | Reject recommendation |
| GET | `/positions` | List active positions (Watchtower) |
| GET | `/heartbeat` | System heartbeat (A-P2-08) |
| POST | `/analyze/batch` | Batch analysis on liquid universe; macro gate and sector exposure applied |
| GET | `/recommendations?check_stale=true` | Include `live_price`, `live_credit`, `thesis_stale` (A-FIX-05) |

## Local development

**Backend** (from repo root; Postgres/Redis running, e.g. `docker compose up -d postgres redis`):

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql+asyncpg://aiadvisor:aiadvisor_dev@localhost:5432/aiadvisor
export PYTHONPATH=.:backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend** (from repo root):

```bash
cd frontend && npm install && npm run dev
# Set NEXT_PUBLIC_API_URL=http://localhost:8000 if API is not on same host
```

## Migrations

From repo root (set `DATABASE_URL` or `alembic.ini`):

```bash
PYTHONPATH=. alembic upgrade head
```

## Layout

| Path | Purpose |
|------|---------|
| `backend/` | FastAPI app, QuantLaws, analysis pipeline, Watchman (APScheduler), batch runner |
| `backend/app/services/` | Ingestion, options chain, regime, LLM synthesis, universe, rate limit, **providers** (MarketDataProvider), **macro_calendar** (MacroCalendarProvider) |
| `database/` | SQLAlchemy models, async session, Alembic migrations |
| `frontend/` | Next.js (React, Tailwind, React Query, sonner): Command Center (Dashboard, Analyst, Queue, Watchtower), dark mode, sidebar |
| `docker-compose.yml` | Postgres, Redis, API, Frontend |

## Environment

- `DATABASE_URL` — PostgreSQL connection (async). Default: `postgresql+asyncpg://aiadvisor:aiadvisor_dev@localhost:5432/aiadvisor`
- `INGESTION_MOCK_MODE` / `ingestion_mock_mode` — `true`: mock market/option data; `false`: use Polygon (implement in services when ready).
- `NEXT_PUBLIC_API_URL` — Frontend: API base URL (default `http://localhost:8000` when using Docker).
- `ALERT_WEBHOOK_URL` — (Optional) Watchman POSTs triggered alerts (21 DTE, stop loss, take profit, strike touch, data stale, ROLL_NEEDED) to this URL.
- `HEARTBEAT_WEBHOOK_URL` — (Optional) Watchman POSTs the system heartbeat every 4 hours to this URL.
- **Strategy/config** (optional overrides): `MACRO_LOOKAHEAD_HOURS` (default 48), `RSI_ENTRY_THRESHOLD` (40), `MIN_YIELD_PCT` (0.20), `ROLL_ITM_PCT` (0.03), `ROLL_DTE_TRIGGER` (14), `MAX_SECTOR_ALLOCATION_PCT` (0.70), `MAX_SKEW_THRESHOLD` (10), `DATA_STALE_MINUTES` (60). See `backend/app/config.py` for full list.
- `TRADING_ECONOMICS_API_KEY` — (Optional) For macro calendar when mock is off; high-impact events within lookahead block new entries.
