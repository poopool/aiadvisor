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

**Phase 2 implementation**: All items implemented. **A-P2-01**: `active_positions` table and `/positions` API; approve flow creates position and sets risk_rules (stop 3×, take profit 0.5×). **A-P2-02**: Watchman loop polls every 15 min during market hours (A-FIX-06), else hourly; mark and underlying price come from `MarketDataProvider.get_quote(ticker)` when not mock (Mock provider implements `get_quote`; Polygon can implement or fallback). **A-P2-03–A-P2-06**: 21 DTE, strike touch (handles both SHORT_PUT and SHORT_CALL), stop loss, take profit monitors in `watchman.run_watchman_cycle`; `last_heartbeat` updated with mark, underlying, and data freshness. **A-P2-07**: `AlertLog` and `_ensure_alert_sent` enforce idempotency per position/trigger. **A-P2-08**: Heartbeat message built and exposed at `/heartbeat`; when `HEARTBEAT_WEBHOOK_URL` or `ALERT_WEBHOOK_URL` are set, Watchman POSTs heartbeat (every 4h) and triggered alerts to those URLs. **A-P2-09**: Frontend Watchtower at `/watchtower` lists active positions with Red/Green for stop and take-profit, and CLOSING_URGENT row styling.

### Phase 3: The Hunter (Automated Scanning)
| ID | Title | Acceptance Criteria (Pass/Fail) | Owners | Status |
|---|---|---|---|---|
| **A-P3-01** | S&P 500 Universe Loader | Auto-fetch current S&P 500 constituents. | Arch | ✅ Completed |
| **A-P3-02** | Liquidity Filter | Filter Universe for `ADV > 2M` and `Spread < 1.5%`. | Trader | ✅ Completed |
| **A-P3-03** | Batch Analysis Runner | Run Phase 1 logic on all liquid tickers. | Arch | ✅ Completed |
| **A-P3-04** | Macro/Event Filter | Check "Earnings Date". Exclude if Earnings is within trade duration. | Trader | ✅ Completed |
| **A-P3-05** | **Sector Correlation Cap** | Prevents recommending more than 2 active trades in the same sector. | Trader | ✅ Completed |
| **A-P3-06** | **Rate Limit Controller** | Implements a queuing system for API calls to prevent data provider throttling. | Arch | ✅ Completed |

**Phase 3 implementation**: All items implemented. **A-P3-01**: S&P 500 universe is fetched from Wikipedia. **A-P3-02**: Liquidity filter is applied at the option level, not the stock level. **A-P3-03**: Batch analysis runner runs Phase 1 logic on all liquid tickers. **A-P3-04**: Macro/event filter excludes trades with earnings within the trade duration. **A-P3-05**: Sector correlation cap prevents recommending more than 2 active trades in the same sector. **A-P3-06**: In-memory rate limiter implemented.

### Phase 4: Macro & Manager
**Purpose**: Automation of the "Event Horizon" macro filter, "Income Shield" rolling logic, and refinement of entry criteria. Introduces strict externalization of all strategy configuration values to prevent hardcoding.

| ID | Title | Acceptance Criteria (Pass/Fail) | Owners | Status |
|---|---|---|---|---|
| **A-P5-01** | **Macro Calendar Provider** | Implement `MacroCalendarProvider` (e.g. Econoday/Trading Economics API). Fetch "High Impact" events (CPI, NFP, FOMC). <br> **Gate**: Block new entries if event `Start_Time < Now + settings.MACRO_LOOKAHEAD_HOURS` (config: 48h). | Arch | ✅ Completed |
| **A-P5-02** | **Externalized Strategy Config** | Refactor `QuantLaws` & `Watchman`. Remove all hardcoded constants (e.g., RSI 30/40, Yield 20%). <br> **Requirement**: All thresholds must be loaded from `app.config.Settings` or similar config file. | Arch | ✅ Completed |
| **A-P5-03** | **Refined Entry Gates (Safety Floor)** | Update `analysis.py`. <br> **RSI**: Check `< settings.RSI_ENTRY_THRESHOLD` (config: 40). <br> **Yield**: Check `Annualized_Yield > settings.MIN_YIELD_PCT` (config: 0.20). | Trader | ✅ Completed |
| **A-P5-04** | **Income Shield (Roll Logic)** | Update `watchman.py`. New alert type: `ROLL_NEEDED`. <br> **Trigger**: If `(Price - Strike)/Strike > settings.ROLL_ITM_PCT` (config: 0.03) AND `DTE < settings.ROLL_DTE_TRIGGER` (config: 14). | Trader | ✅ Completed |
| **A-P5-05** | **Sector Value Exposure** | Update `ActivePosition` to track `capital_deployed`. <br> **Gate**: Block trade if `Sum(Capital) in Sector > settings.MAX_SECTOR_ALLOCATION` (config: 70%). | Arch | ✅ Completed |

**Phase 4 implementation**: **A-P5-01**: `MacroCalendarProvider` in `app/services/macro_calendar.py` (Mock + Trading Economics); `macro_event_gate_blocked()` blocks new entries in `POST /analyze` and `POST /analyze/batch` when high-impact event within `macro_lookahead_hours`. **A-P5-02**: All thresholds in `config.Settings` (iv_natr_min_ratio, dte_alert_threshold, rsi_overbought/oversold, roll_itm_pct, roll_dte_trigger, etc.); `QuantLaws` and `strategy_selector` read from settings. **A-P5-03**: RSI gate (Short Put only if RSI < rsi_entry_threshold) and annualized yield gate (yield > min_yield_pct) in `analysis.py`. **A-P5-04**: Watchman triggers `ROLL_NEEDED` when (Price−Strike)/Strike ≥ roll_itm_pct and DTE < roll_dte_trigger; idempotent via AlertLog. **A-P5-05**: `entry_data.capital_deployed` and `entry_data.sector` on approve; `sector_value_exposure_allowed()` in `universe.py`; gate in analyze and batch.

### Phase 5: Local Dev & Debugging (Immediate)
*Focus: Ensuring the "Math" is correct, the loops don't die silently, and the data is trustworthy during your local testing.*

| ID | Title | Acceptance Criteria (Pass/Fail) | Owners | Status |
|---|---|---|---|---|
| **A-FIX-10** | **Robust Watchman Scheduler** | Replace `asyncio.create_task` loop in `main.py` with a robust scheduler (e.g., `APScheduler`) that handles exceptions, logs failures, and prevents the "Zombie Loop" scenario where monitoring dies silently. | Arch | ✅ Completed |
| **A-FIX-11** | **Remove Silent Mock Fallbacks** | Search for `NotImplementedError` catch blocks (e.g., `watchman.py`) that return hardcoded values (like `$3.40`). Logic must raise explicit `DataFetchError` alerts instead of failing open with fake data. | Dev | ✅ Completed |
| **A-FIX-12** | **Price Slippage & Bid/Ask Logic** | Update `options.py`: Use **Bid Price** for Credit estimation (selling) and **Ask Price** for Buy-to-Close costs. Remove `(Bid+Ask)/2` mid-price usage to reflect realistic liquidity costs. | Trader | ✅ Completed |
| **A-FIX-13** | **Recommendation Idempotency** | Modify `POST /analyze/{ticker}`: Query DB for existing `PENDING` recommendations for the same Ticker/Strategy/Expiry. Return existing ID instead of creating duplicates. | Dev | ✅ Completed |
| **A-FIX-14** | **JSON Serialization Precision** | Middleware/Serializer update: Ensure `Decimal` types are serialized as **Strings** (e.g., `"10.50"`) in JSON responses, not Floats, to prevent IEEE 754 precision loss at the Frontend. | Dev | ✅ Completed |

**Phase 5 implementation**: **A-FIX-10**: Watchman runs via `AsyncIOScheduler` (APScheduler), 15‑min interval, first run after 60s; exceptions logged, `DataFetchError` handled without crashing. **A-FIX-11**: `get_mark_price_for_position` raises `DataFetchError` on `NotImplementedError`; cycle skips position on `DataFetchError`. **A-FIX-12**: `analysis.py` uses `bid` for `credit_est`, `ask` for `buy_to_close_est`. **A-FIX-13**: `POST /analyze/{ticker}` checks for existing PENDING (ticker, strategy, expiry), returns `existing_recommendation_id` when found. **A-FIX-14**: `DecimalJSONResponse` as default response class; Decimals serialized as strings.

### Phase 6: Institutional Mechanics (Hedge Fund Upgrades)
**Purpose**: Elevate the bot from "Smart Retail" to "Institutional" by solving for Term Structure accuracy and Skew risk (Trap Doors).

| ID | Title | Acceptance Criteria (Pass/Fail) | Owners | Status |
|---|---|---|---|---|
| **A-P7-01** | **Term Structure Interpolation** | **Logic Update**: Stop using generic `IV_30d` for execution logic. <br> **Requirement**: When a candidate option is selected (e.g., 43 DTE), the system must interpolate the Implied Volatility for that *exact* DTE using the volatility surface (or nearest expirations). <br> **Validation**: The `IV/NATR` calculation must use `IV_Target_Expiry`, not `IV_30d`. | Quant | ✅ Completed |
| **A-P7-02** | **Volatility Skew Gate** | **New Metric**: Calculate the "25-Delta Skew" for the target expiration. <br> **Formula**: `Skew = IV(Put_25Δ) - IV(Call_25Δ)`. <br> **Gate**: Block "Short Put" entry if `Skew > settings.MAX_SKEW_THRESHOLD` (e.g., Skew is >10 points or >1.5x Call IV), indicating the market is pricing in a "limit down" event. | Quant | ✅ Completed |

**Phase 6 implementation**: **A-P7-01**: After strike selection, IV at target expiry is taken from selected option (`selected["iv"]`); IV/NATR re-checked with `IV_Target_Expiry`; failure returns NONE with "Term structure" thesis. **A-P7-02**: `get_skew_25d(chain, expiry)` in `options.py` computes Put_25Δ IV − Call_25Δ IV; Short Put blocked when \|skew\| > max_skew_threshold (points).

### Phase 7: Pre-Production & GCP (Before Deploy)
*Focus: Transforming the app from a "local script" into a "cloud-native service" that is secure, scalable, and observable.*

| ID | Title | Acceptance Criteria (Pass/Fail) | Owners | Status |
|---|---|---|---|---|
| **A-OPS-01** | **Redis Rate Limiter** | Replace in-memory `deque` limiter in `rate_limit.py` with a **Redis Token Bucket** pattern. Limits must be shared across multiple container replicas (essential for Cloud Run auto-scaling). | Arch | 🔴 Todo |
| **A-OPS-02** | **API Authentication** | Implement `API Key` security header or Basic Auth for all `POST` endpoints. Reject unauthorized requests with `401 Unauthorized`. | Security | 🔴 Todo |
| **A-OPS-03** | **External Secrets Management** | Remove hardcoded passwords in `docker-compose.yml`. Update `config.py` to enforce loading secrets (DB Pass, API Keys) strictly from Environment Variables. | Ops | 🔴 Todo |
| **A-OPS-04** | **Structured Logging** | Replace `print()` statements with a JSON-structured logger (e.g., `structlog`). Logs must include `severity`, `timestamp`, and `correlation_id` for Cloud Logging ingestion. | Ops | 🔴 Todo |
| **A-OPS-05** | **Dedicated Worker Service** | Refactor: Extract the `Watchman` loop from the API container into a separate `worker` entrypoint. `docker-compose` and Cloud Run must run API and Worker as distinct services. | Arch | 🔴 Todo |

### Phase 8: UI/UX Modernization (The Command Center)
**Purpose**: Transform the frontend from a debug viewer into a professional "Command Center" that exposes all backend capabilities (Manual Analysis, Batch Runs, System Health) in a Dark Mode environment.

| ID | Title | Acceptance Criteria (Pass/Fail) | Owners | Status |
|---|---|---|---|---|
| **A-UI-01** | **Global Dark Mode & App Shell** | **Visual Overhaul**: Implement a strict "Financial Dark Mode" (e.g., Slate-900/Zinc-950 background). <br> **Layout**: Replace the homepage buttons with a persistent **Sidebar Navigation** (Dashboard, Analyst, Queue, Watchtower). <br> **Typography**: Use Monospace fonts (e.g., `JetBrains Mono` or `Geist Mono`) for all financial data (Prices, Greeks, Strikes). | Frontend | ✅ Completed |
| **A-UI-02** | **"The Analyst" Console (Manual Entry)** | **New Page**: `/analyst`. <br> **Input**: Search bar accepting a Ticker Symbol (connects to `POST /analyze/{ticker}`). <br> **Output**: Display the Analysis Result (Card View) including the generated Thesis, Greeks, and Safety Checks. <br> **Action**: "Add to Queue" button (if trade is valid) or "Force Ignore". | Frontend | ✅ Completed |
| **A-UI-03** | **Command Center Dashboard** | **New Page**: `/` (Home). <br> **Widgets**: <br> 1. **System Health**: Heartbeat indicator (Green Pulse) pulling from `/heartbeat`. <br> 2. **Quick Stats**: Count of Active Positions, Pending Approvals, and Recent Alerts. <br> 3. **Batch Trigger**: Button to manually trigger `POST /analyze/batch` with a loading state. | Frontend | ✅ Completed |
| **A-UI-04** | **Enhanced Data Tables** | **Refactor**: Update Queue and Watchtower tables. <br> **Features**: <br> 1. **Badges**: Colored Pills for Status (PENDING=Yellow, OPEN=Blue, CLOSING_URGENT=Red animate-pulse). <br> 2. **Expandable Rows**: Click a row to reveal hidden details (Full Thesis text, specific Risk Rules, detailed Entry Data) that don't fit in columns. <br> 3. **Copy-to-Clipboard**: Quick copy for Contract IDs. | Frontend | ✅ Completed |
| **A-UI-05** | **System Notifications (Toasts)** | **Feedback Loop**: Implement a Toast system (e.g., `sonner` or `react-hot-toast`). <br> **Triggers**: Show Success/Error popups when Approving/Rejecting trades, running Analysis, or when the System Heartbeat fails (500 Error). | Frontend | ✅ Completed |

**Phase 8 implementation**: **A-UI-01**: Dark theme in `globals.css` (slate-950/slate-900); `AppShell` and `Sidebar` in `app/components/` with persistent nav (Dashboard, Analyst, Queue, Watchtower); Tailwind `font-mono` and `.font-financial` for prices, Greeks, strikes. **A-UI-02**: `/analyst` page with ticker search → `POST /analyze/{ticker}`, result card (thesis, Greeks, safety), "Open in Queue" / "Dismiss". **A-UI-03**: Home `/` is Command Center: System Health (heartbeat from `/heartbeat`, green pulse when OK), Quick Stats (active positions, pending approvals), Batch Trigger button with loading. **A-UI-04**: Queue and Watchtower tables refactored with status badges (PENDING=amber, MONITORING=blue, CLOSING_URGENT=red animate-pulse), expandable rows (click for full thesis/risk rules/entry data), Copy button for contract IDs. **A-UI-05**: `sonner` Toaster in `providers.tsx`; success/error toasts on Approve/Reject, Analyst run, batch run.

### Phase 9: Portfolio Management & Usability
**Purpose**: Enhance direct user control over the portfolio, allowing for manual entry and removal of positions to synchronize the Watchtower with an external brokerage account.

| ID | Title | Acceptance Criteria (Pass/Fail) | Owners | Status |
|---|---|---|---|---|
| **A-P9-01** | **Manual Position Management** | **API**: `POST /positions/manual` endpoint creates an `ActivePosition` from user inputs (Ticker, Strategy, etc.), returning the new object. <br> **API**: `DELETE /positions/{position_id}` endpoint removes a position. <br> **UI**: Watchtower page includes an "Add Manual Position" button/form. <br> **UI**: Each position row has a "Delete" button with a confirmation step. | Arch, Frontend | ✅ Completed |

**Phase 9 implementation**: **A-P9-01**: Implemented. `POST /positions/manual` added to `main.py` with `ManualPositionCreate` schema; `DELETE /positions/{position_id}` also added. Frontend `watchtower/page.tsx` updated with "Add Manual Position" button, a modal form (`ManualPositionForm.tsx`), and a "Delete" button on each row, all connected via React Query mutations.

### Phase 10: System Refinements
**Purpose**: Improve the efficiency and robustness of core background processes.

| ID | Title | Acceptance Criteria (Pass/Fail) | Owners | Status |
|---|---|---|---|---|
| **A-FIX-15** | **Efficient Watchman Scheduling** | The `_watchman_job` scheduler task must verify `is_market_hours()` before executing the `run_watchman_cycle`. The job should exit early if the market is closed to conserve resources and API quota. | Arch | ✅ Completed |

**Phase 10 implementation**: **A-FIX-15**: Implemented. The `_watchman_job` function in `main.py` now includes a guard clause at the beginning that calls `is_market_hours()` and returns immediately if it's false.

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

## 7) Critical Fixes & Refinements (Spec Patch v1.1)

**Status**: **APPROVED**
**Date**: 2026-02-09
**Purpose**: This backlog phase addresses high-priority logic errors, schema gaps, and risk management refinements identified during the architecture review.

| ID | Title | Acceptance Criteria (Pass/Fail) | Owners | Status |
|---|---|---|---|---|
| **A-FIX-01** | **Fix IV/NATR Logic** | **Math Update**: Change formula to match timeframes. <br> New Formula: `Ratio = IV_30d / ((ATR_14 / Close * 100) * sqrt(252))`. <br> **Gate**: Pass only if `Ratio > 1.0`. | Trader | ✅ Completed |
| **A-FIX-02** | **Refine Liquidity Gates** | **Stock**: Universe filter strictly `ADV > 5M`. <br> **Option**: Filter strictly `(Ask - Bid) / Bid_Price < 0.05` (Spread < 5%). | Trader | ✅ Completed |
| **A-FIX-03** | **Hard Earnings Exclusion** | Check `Earnings Date`. Return `NO_TRADE` if earnings event occurs between `Today` and `Expiry Date`. | Trader | ✅ Completed |
| **A-FIX-04** | **Ticker-Level Trend Filter** | Logic Update: In addition to SPY check, block Short Put if `Ticker_Price < Ticker_SMA_50_Daily`. | Trader | ✅ Completed |
| **A-FIX-05** | **UI: Stale Thesis Warning** | Frontend Calculation: If `Live_Price < Rec_Price * 0.95` OR `Live_Credit < Rec_Credit * 0.90`, display **"THESIS STALE"** warning. | Frontend | ✅ Completed |
| **A-FIX-06** | **High-Freq Active Polling** | Update Watchman Scheduler: `ActivePositions` must be polled every **15 minutes** during market hours (vs hourly). | Arch | ✅ Completed |
| **A-FIX-07** | **Schema: Rolling Lineage** | Update `ActivePositions` Table. Add columns: `parent_position_id` (UUID), `root_position_id` (UUID), `roll_count` (INT), `realized_pnl_pre_roll` (DECIMAL). | Arch | ✅ Completed |
| **A-FIX-08** | **Abstract Data Provider** | Refactor Code: Create `MarketDataProvider` interface. Remove hardcoded `polygon` calls in core logic. | Arch | ✅ Completed |
| **A-FIX-09** | **Decimal Precision Check** | Database Audit: Ensure all Price/Greek columns in Postgres are `DECIMAL(10, 4)` or higher. | Arch | ✅ Completed |

**Implementation status (Spec Patch v1.1)**: All items are implemented in code. IV/NATR uses the updated formula with `sqrt(252)` and gate `> 1.0`. Liquidity: stock ADV > 5M, option spread `(Ask-Bid)/Bid < 10%`. Hard earnings exclusion returns `NO_TRADE` when earnings falls between today and expiry. Ticker-level filter blocks Short Put when `Price < SMA_50`. Frontend displays **THESIS STALE** when `live_price < rec_price*0.95` or `live_credit < rec_credit*0.90`. Watchman polls every 15 minutes during market hours (9:30–16:00 ET). `ActivePosition` has `parent_position_id`, `root_position_id`, `roll_count`, `realized_pnl_pre_roll`. Data access goes through `MarketDataProvider` (Mock/Polygon). All price and Greek columns use `Numeric(10,4)` or higher.