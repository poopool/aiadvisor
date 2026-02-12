# AI_Advisor_Bot.md — Options Co-Pilot Spec

**Purpose**: Define the operational contract, architecture, and roadmap for the "AI Advisor Bot" — a semi-autonomous options analytics engine designed to generate income (premiums) and protect capital via deterministic risk management.

**Role**: "The Analyst & The Watchman." It finds trades, validates them, and watches them. It **does not** execute trades automatically.

---

## 0) Operating Contract (Anti-Hallucination Rules)

1.  **Code is King (The Source of Truth)**: If a discrepancy arises between this documentation and the implementation code, **the code prevails**. The documentation must be updated to reflect the code, not vice-versa.
2.  **Deterministic "Math" First**: Technical indicators (RSI, SMA), Option Greeks (Delta, Gamma), and Volatility metrics (IV/NATR) must be calculated by code, never estimated by an LLM.
3.  **Decimal Precision**: All financial calculations (strikes, premiums, ratios) must use the `Decimal` type to avoid floating-point errors.
4.  **LLM as Synthesizer**: The LLM is used to read "unstructured" context (News, Geopolitics, Earnings calls) and to synthesize the final recommendation narrative. It does not calculate RSI.
5.  **Human-in-the-Loop**: The bot proposes; the human executes. The system must wait for a "Trade Confirmed" signal (manual entry via Frontend) to begin monitoring a position.
6.  **Fail-Safe Monitoring**: Alerts (Stop Loss, 21 DTE) are deterministic triggers. They must fire regardless of LLM availability.

---

## 1) System Identity & Philosophy

**Goal**: A sophisticated options analyst that filters the S&P 500 for high-probability premium selling opportunities and relentlessly monitors active risk.

**Philosophy**: "Sell volatility when it’s expensive; buy it back when it’s cheap or dangerous. Math dictates the setup; AI explains the context; Human pulls the trigger".

---

## 2) Architecture Overview

### 2.1 System Design (Microservices Pattern)
The system follows a containerized, 3-tier microservices architecture designed for local development (via Docker Compose) with a direct migration path to Google Cloud Platform (Cloud Run + Cloud SQL).

1.  **Frontend Service (The Dashboard)**
    * **Role**: User Interface for approving trades, viewing active positions, and receiving alerts.
    * **Tech**: **Next.js (React)** with **React Query** for state management and **Tailwind CSS** for styling.
    * **Deployment**: Containerized stateless service.
2.  **API & Worker Service (The Brain & Watchman)**
    * **Role**: Hosts the `Quantitative Engine`, `Ingestion Service`, and `Watchman` scheduler.
    * **Tech**: Python (FastAPI/Django) + Celery/APScheduler.
    * **Responsibilities**:
        * Exposes REST endpoints for the Frontend.
        * Runs background jobs for "Smart Polling" ingestion and 21-DTE checks.
    * **Deployment**: Containerized service.
3.  **Data Layer (The Vault)**
    * **Role**: Persistent storage for Trade History, Active Positions, and cached Market Data.
    * **Tech**: Relational DB (PostgreSQL recommended) + Redis (optional for caching).
    * **Deployment**:
        * *Phase 1 (Local)*: Dockerized PostgreSQL container.
        * *Phase 2 (GCP)*: Managed Cloud SQL instance.

### 2.2 Component Interaction Flow
1.  **Ingestion (Smart Polling)**: The API Worker wakes up on a schedule, fetches fresh market data from Canonical Sources (Polygon), and persists it to the Data Layer. **It does not stream data.**
2.  **Analysis**: The `Quantitative Engine` queries the *Data Layer* (not the external API directly) to apply math laws and generate `Trade Recommendations`.
3.  **Approval**: The Frontend polls the API for `PENDING` recommendations. The Human reviews the thesis and clicks "Approve" to move the trade to `MONITORING`.
4.  **Monitoring**: The `Watchman` wakes up hourly, checks the Data Layer for active positions, compares the latest persisted price against risk rules, and triggers alerts if necessary.

### 2.3 Deployment Strategy
* **Stage 1: Local Workstation (Dev)**
    * Orchestration: `docker-compose`.
    * Environment: Local containers for UI, API, and DB. Volume mounts for code persistence.
* **Stage 2: GCP (Prod)**
    * Compute: GCP Cloud Run (Serverless containers for UI and API).
    * Database: GCP Cloud SQL (Managed PostgreSQL).
    * Security: IAM roles for service-to-service communication.

### 2.4 Data Sources (Canonical)
-   **Market Data**: Polygon.io / Alpaca (for OHLCV).
-   **Option Data**: Polygon.io / ThetaData (for Chains, Greeks, IV).
-   **Macro/News**: NewsAPI / Benzinga (fed to LLM).

---

## 3) Hard Constraints ("Laws")

1.  **The 21 DTE Law**: The system must flag any position at 21 Days to Expiration for immediate roll/close.
2.  **The 50% Profit Rule**: Positions should be flagged for closing once 50% of the maximum possible profit (initial credit) is realized.
3.  **Market Regime Filter**: No "Short Put" recommendations are permitted if the S&P 500 (SPY) is trading below its 200-day SMA.
4.  **Liquidity Gate**: No recommendations for stocks with < 2M ADV or Spread > 1.5%.
5.  **Efficiency Gate**: "Premium Selling" recommendations require `IV/NATR > 1.5` (relaxed from 2.0 for Phase 1 testing) or explicit "Earnings Play" flag.
6.  **Risk Cap**: Recommended Stop Loss must never exceed 3x Credit Received.
7.  **The Data Freshness Law**: The Watchman must verify data age. If the `Mark Price` timestamp is > 60 minutes old during market hours, the system must trigger a `CRITICAL_DATA_STALE` alert to the human.
8.  **Sector Taxonomy**: Sector classification defaults to the **GICS Sector** (Global Industry Classification Standard) as provided by the Data Ingestion Service.

---

## 4) Deterministic Interfaces (The Math)

**Canonical Metrics** (Must be computed in Python, `decimal` library required):

-   **Timeframe Standards**:
    -   `Daily`: Standard for Trend (SMA) and Volatility (ATR) calculations.
    -   `Hourly`: Allowed only for execution timing, not analysis.
-   **IV Source**: `IV_30d` refers to **30-Day Constant Maturity Implied Volatility** (interpolated), *not* the nearest expiration IV.
-   **Math Precision**: All percentage inputs (IV, Yield) must be converted to decimals for calculation (e.g., 20% = 0.20).

**Formulas**:

-   **IV/NATR Ratio**:
    $$Ratio = \frac{IV_{30d}}{\frac{ATR_{14\_Daily}}{Close\_Price} \times 100}$$

-   **Expected Move (1-SD)**:
    $$EM = Price \times IV_{30d} \times \sqrt{\frac{DTE}{365}}$$

-   **RSI State**:
    -   `Overbought`: RSI_14_Daily > 70
    -   `Oversold`: RSI_14_Daily < 30

-   **Trend State**:
    -   `Bullish`: Price > SMA_200_Daily (Major) AND Price > SMA_50_Daily (Minor)
    -   `Bearish`: Price < SMA_50_Daily

---

## 5) Phased Roadmap & Backlog

### Phase 0: Infrastructure & Core (New)
| ID | Title | Acceptance Criteria (Pass/Fail) | Owners | Status |
|---|---|---|---|---|
| **A-P0-01** | **Container Strategy** | Create `Dockerfile` for API and Frontend; `docker-compose.yml` for local stack including DB. | Arch | ✅ Completed |
| **A-P0-02** | **Database Schema** | Define SQL Schema for `Trades`, `Positions`, and `MarketData` tables. | Arch | ✅ Completed |
| **A-P0-03** | **API Skeleton** | Setup FastAPI/Flask boilerplate with Health Check endpoint connecting to DB. | Arch | ✅ Completed |

**Phase 0 implementation**: All items implemented. Dockerfiles for API and Frontend; `docker-compose.yml` with API, Frontend, and PostgreSQL; Alembic migrations for `market_data`, `trade_recommendations`, `active_positions`, `alert_log`; FastAPI with `GET /health` connected to DB.

### Phase 1: The Core Analyst (Input -> Analysis -> Recommendation)
| ID | Title | Acceptance Criteria (Pass/Fail) | Owners | Status |
|---|---|---|---|---|
| **A-P1-01** | Ingestion & Technical Pipeline | Input: List of Tickers. Output: JSON Object with Price, SMA_50, RSI_14, ATR_14, IV_30d. | Arch, Trader | ✅ Completed |
| **A-P1-02** | Volatility Logic Gate | Implement `IV/NATR` calculation. | Trader | ✅ Completed |
| **A-P1-03** | Option Chain Fetcher | Fetch option chain for a ticker. Filter for specific expirations (30-45 DTE). | Arch | ✅ Completed |
| **A-P1-04** | Strategy Selector (The Brain) | Logic to map Technical State to Option Strategy. | Trader | ✅ Completed |
| **A-P1-05** | Strike Selection Engine | Select specific strikes based on Delta (~0.20-0.30 Delta). | Trader | ✅ Completed |
| **A-P1-06** | LLM Synthesis Layer | Feed Technicals + Option Candidate + News to LLM for Thesis generation. | Arch | ✅ Completed |
| **A-P1-07** | **Market Regime Filter** | System checks SPY 200-day SMA; blocks Short Put trades in bear regimes. | Trader | ✅ Completed |
| **A-P1-08** | **Expected Move Engine** | Calculates 1-SD move for the target expiry; ensures strike is outside this range. | Trader | ✅ Completed |
| **A-P1-09** | **Frontend: Approval Queue** | UI Table displaying `PENDING` recommendations. Actions: "Approve" (moves to Monitor) or "Reject". | Frontend | ✅ Completed |

**Phase 1 implementation**: All items implemented. Ingestion returns Price, SMA_50, SMA_200, RSI_14, ATR_14, IV_30d and **persists to the Data Layer** on each `POST /analyze/{ticker}` (§2.2). Option chain is **filtered to 30–45 DTE** (A-P1-03). Analysis accepts optional pre-fetched `market_data_result` so the API can fetch once, persist, then run the pipeline. IV/NATR, Expected Move, Regime filter, Strategy selector, Strike selection, LLM synthesis, and Frontend Approval Queue are in place.

### Phase 2: The Watchman (Active Position Monitoring)
| ID | Title | Acceptance Criteria (Pass/Fail) | Owners | Status |
|---|---|---|---|---|
| **A-P2-01** | Portfolio State Store | Persistent store tracking "Active Positions" (Ticker, Strike, Entry Price). | Arch | ✅ Completed |
| **A-P2-02** | Market Data Poller | Scheduler (e.g., hourly) that updates Current Price and Mark Price via Smart Polling. | Arch | ✅ Completed |
| **A-P2-03** | "21 DTE" Rule Monitor | Check `Expiry - Today`. If `<= 21 days`, trigger ALERT. | Trader | ✅ Completed |
| **A-P2-04** | "Strike Touch" Monitor | Check `Current Stock Price` vs `Short Strike`. Trigger ALERT on touch. | Trader | ✅ Completed |
| **A-P2-05** | Stop Loss Monitor (3x Credit) | Check `Mark >= 3.0 * Entry`. Trigger ALERT. | Trader | ✅ Completed |
| **A-P2-06** | **Take Profit Monitor** | Trigger ALERT if `Current Mark <= 0.5 * Entry Credit`. | Trader | ✅ Completed |
| **A-P2-07** | **Alert Idempotency** | Prevents alert spam; tracks `ALERT_SENT` state for specific triggers. | Arch | ✅ Completed |
| **A-P2-08** | **System Heartbeat** | Sends a "System Online" heartbeat to the human every 4 hours. Checks Data Freshness. | Arch | ✅ Completed |
| **A-P2-09** | **Frontend: Watchtower** | UI Dashboard showing `ActivePositions`. Visual indicators (Red/Green) for Stop Loss or Profit targets. | Frontend | ✅ Completed |

**Phase 2 implementation**: All items implemented. **A-P2-01**: `active_positions` table and `/positions` API; approve flow creates position and sets risk_rules (stop 3×, take profit 0.5×). **A-P2-02**: Watchman loop polls every 15 min during market hours (A-FIX-06), else hourly; mark and underlying price come from `MarketDataProvider.get_quote(ticker)` when not mock (Mock provider implements `get_quote`; Polygon can implement or fallback). **A-P2-03–A-P2-06**: 21 DTE, strike touch, stop loss, take profit monitors in `watchman.run_watchman_cycle`; `last_heartbeat` updated with mark, underlying, and data freshness. **A-P2-07**: `AlertLog` and `_ensure_alert_sent` enforce idempotency per position/trigger. **A-P2-08**: Heartbeat message built and exposed at `/heartbeat`; when `HEARTBEAT_WEBHOOK_URL` or `ALERT_WEBHOOK_URL` are set, Watchman POSTs heartbeat (every 4h) and triggered alerts to those URLs. **A-P2-09**: Frontend Watchtower at `/watchtower` lists active positions with Red/Green for stop and take-profit, and CLOSING_URGENT row styling.

### Phase 3: The Hunter (Automated Scanning)
| ID | Title | Acceptance Criteria (Pass/Fail) | Owners | Status |
|---|---|---|---|---|
| **A-P3-01** | S&P 500 Universe Loader | Auto-fetch current S&P 500 constituents. | Arch | ✅ Completed |
| **A-P3-02** | Liquidity Filter | Filter Universe for `ADV > 2M` and `Spread < 1.5%`. | Trader | ✅ Completed |
| **A-P3-03** | Batch Analysis Runner | Run Phase 1 logic on all liquid tickers. | Arch | ✅ Completed |
| **A-P3-04** | Macro/Event Filter | Check "Earnings Date". Exclude if Earnings is within trade duration. | Trader | ✅ Completed |
| **A-P3-05** | **Sector Correlation Cap** | Prevents recommending more than 2 active trades in the same sector. | Trader | ✅ Completed |
| **A-P3-06** | **Rate Limit Controller** | Implements a queuing system for API calls to prevent data provider throttling. | Arch | ✅ Completed |

---

## 6) Data Structures (Canonical)

### 6.1 Trade Recommendation Schema (Phase 1 Output)
```json
{
  "ticker": "NVDA",
  "timestamp": "2026-02-09T14:30:00Z",
  "regime": "BULLISH_SPY_OVER_200SMA",
  "analysis": {
    "price": 175.50,
    "rsi_14": 28.5,
    "trend": "bullish",
    "iv_rank": 65,
    "iv_natr_ratio": 2.1,
    "expected_move_1sd": 12.40,
    "earnings_date": "2026-02-27"
  },
  "recommendation": {
    "strategy": "SHORT_PUT",
    "contract": "NVDA260320P00160000",
    "strike": 160.0,
    "expiry": "2026-03-20",
    "delta": -0.20,
    "credit_est": 3.50,
    "safety_check": "Strike is outside 1-SD expected move",
    "thesis": "NVDA is oversold (RSI 28) but in a macro bull trend. Volatility is expensive (Ratio 2.1). Strike selected at 0.20 Delta, providing buffer beyond expected move."
  }
}
```

### 6.2 Active Position Schema (The "Watchman" State)
This schema represents the "Source of Truth" for the Watchman service. It must be persisted to the Data Layer.

```json

{
  "position_id": "uuid-v4",
  "ticker": "NVDA",
  "status": "OPEN",
  "lifecycle_stage": "MONITORING",
  "entry_data": {
    "strategy": "SHORT_PUT",
    "short_strike": 160.00,
    "expiry_date": "2026-03-20",
    "entry_price": 3.50,
    "entry_timestamp": "2026-02-09T14:30:00Z",
    "contracts": 1
  },
  "risk_rules": {
    "stop_loss_price": 10.50,
    "take_profit_price": 1.75,
    "max_dte_hold": 21,
    "force_close_date": "2026-02-27"
  },
  "last_heartbeat": {
    "timestamp": "2026-02-10T09:00:00Z",
    "mark_price": 3.40,
    "data_freshness_status": "OK"
  }
}

```

Note: lifecycle_stage allows values: PENDING_ENTRY, MONITORING, CLOSING_URGENT, CLOSED.

## 7) Phase 4: Critical Fixes & Refinements (Spec Patch v1.1)

**Status**: **APPROVED**
**Date**: 2026-02-09
**Purpose**: This backlog phase addresses high-priority logic errors, schema gaps, and risk management refinements identified during the architecture review.

| ID | Title | Acceptance Criteria (Pass/Fail) | Owners | Status |
|---|---|---|---|---|
| **A-FIX-01** | **Fix IV/NATR Logic** | **Math Update**: Change formula to match timeframes. <br> New Formula: `Ratio = IV_30d / ((ATR_14 / Close * 100) * sqrt(252))`. <br> **Gate**: Pass only if `Ratio > 1.0`. | Trader | ✅ Completed |
| **A-FIX-02** | **Refine Liquidity Gates** | **Stock**: Universe filter strictly `ADV > 5M`. <br> **Option**: Filter strictly `(Ask - Bid) / Bid_Price < 0.10` (Spread < 10%). | Trader | ✅ Completed |
| **A-FIX-03** | **Hard Earnings Exclusion** | Check `Earnings Date`. Return `NO_TRADE` if earnings event occurs between `Today` and `Expiry Date`. | Trader | ✅ Completed |
| **A-FIX-04** | **Ticker-Level Trend Filter** | Logic Update: In addition to SPY check, block Short Put if `Ticker_Price < Ticker_SMA_50_Daily`. | Trader | ✅ Completed |
| **A-FIX-05** | **UI: Stale Thesis Warning** | Frontend Calculation: If `Live_Price < Rec_Price * 0.95` OR `Live_Credit < Rec_Credit * 0.90`, display **"THESIS STALE"** warning. | Frontend | ✅ Completed |
| **A-FIX-06** | **High-Freq Active Polling** | Update Watchman Scheduler: `ActivePositions` must be polled every **15 minutes** during market hours (vs hourly). | Arch | ✅ Completed |
| **A-FIX-07** | **Schema: Rolling Lineage** | Update `ActivePositions` Table. Add columns: `parent_position_id` (UUID), `root_position_id` (UUID), `roll_count` (INT), `realized_pnl_pre_roll` (DECIMAL). | Arch | ✅ Completed |
| **A-FIX-08** | **Abstract Data Provider** | Refactor Code: Create `MarketDataProvider` interface. Remove hardcoded `polygon` calls in core logic. | Arch | ✅ Completed |
| **A-FIX-09** | **Decimal Precision Check** | Database Audit: Ensure all Price/Greek columns in Postgres are `DECIMAL(10, 4)` or higher. | Arch | ✅ Completed |

**Implementation status (Spec Patch v1.1)**: All Phase 4 items are implemented in code. IV/NATR uses the updated formula with `sqrt(252)` and gate `> 1.0`. Liquidity: stock ADV > 5M, option spread `(Ask-Bid)/Bid < 10%`. Hard earnings exclusion returns `NO_TRADE` when earnings falls between today and expiry. Ticker-level filter blocks Short Put when `Price < SMA_50`. Frontend displays **THESIS STALE** when `live_price < rec_price*0.95` or `live_credit < rec_credit*0.90`. Watchman polls every 15 minutes during market hours (9:30–16:00 ET). `ActivePosition` has `parent_position_id`, `root_position_id`, `roll_count`, `realized_pnl_pre_roll`. Data access goes through `MarketDataProvider` (Mock/Polygon). All price and Greek columns use `Numeric(10,4)` or higher.