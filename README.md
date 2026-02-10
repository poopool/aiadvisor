# AI Advisor Bot

Semi-autonomous options analytics engine: **Phase 0–3** and **Phase 4 (Spec Patch v1.1)**. See **PROJECT_CONTEXT.md** for the full spec and backlog.

## Features (by phase)

- **Phase 0**: Docker Compose stack (API, Frontend, Postgres, Redis), DB schema (MarketData, TradeRecommendations, ActivePositions, AlertLog), FastAPI health check.
- **Phase 1**: Ingestion (Price, SMA_50, RSI_14, ATR_14, IV_30d), option chain (30–45 DTE), strategy selector, strike selection by delta, LLM thesis stub, market regime filter (SPY 200 SMA), expected move engine, **Frontend Approval Queue** (PENDING → Approve/Reject).
- **Phase 2**: **Portfolio state** (ActivePosition), **Watchman** (21 DTE, stop loss, take profit, data freshness), alert idempotency, heartbeat; **Frontend Watchtower** (active positions).
- **Phase 3**: S&P 500 universe loader, liquidity filter, **batch analysis** runner, earnings filter, sector correlation cap, rate limit controller.
- **Phase 4 (Spec Patch v1.1)**: IV/NATR formula with `sqrt(252)` and gate > 1.0; liquidity ADV > 5M and option spread < 10%; hard earnings exclusion (NO_TRADE); ticker-level trend filter (block Short Put if Price < SMA_50); **THESIS STALE** warning in Approval Queue; Watchman every **15 min** during market hours; **rolling lineage** on ActivePosition (`parent_position_id`, `root_position_id`, `roll_count`, `realized_pnl_pre_roll`); **MarketDataProvider** abstraction; decimal precision audit (DECIMAL(10,4)+).

## Run the stack (Docker)

```bash
# From repo root
docker compose up -d

# API
open http://localhost:8000
# Docs: http://localhost:8000/docs

# Frontend (Next.js)
open http://localhost:3000
# Approval Queue: http://localhost:3000/approval-queue
# Watchtower:    http://localhost:3000/watchtower
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | DB status, mock_ingestion flag |
| POST | `/analyze/{ticker}` | Run analysis for one ticker; returns §6.1 recommendation, persists as PENDING |
| GET | `/recommendations?status=PENDING` | List recommendations (Approval Queue) |
| POST | `/recommendations/{id}/approve` | Approve → create ActivePosition, move to Monitor |
| POST | `/recommendations/{id}/reject` | Reject recommendation |
| GET | `/positions` | List active positions (Watchtower) |
| GET | `/heartbeat` | System heartbeat (A-P2-08) |
| POST | `/analyze/batch` | Batch analysis on liquid universe (Phase 3) |
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
| `backend/` | FastAPI app, QuantLaws, analysis pipeline, Watchman, batch runner |
| `backend/app/services/` | Ingestion, options chain, regime, LLM synthesis, universe, rate limit, **providers** (MarketDataProvider) |
| `database/` | SQLAlchemy models, async session, Alembic migrations |
| `frontend/` | Next.js (React, Tailwind, React Query): Approval Queue, Watchtower |
| `docker-compose.yml` | Postgres, Redis, API, Frontend |

## Environment

- `DATABASE_URL` — PostgreSQL connection (async). Default: `postgresql+asyncpg://aiadvisor:aiadvisor_dev@localhost:5432/aiadvisor`
- `INGESTION_MOCK_MODE` / `ingestion_mock_mode` — `true`: mock market/option data; `false`: use Polygon (implement in services when ready).
- `NEXT_PUBLIC_API_URL` — Frontend: API base URL (default `http://localhost:8000` when using Docker).
