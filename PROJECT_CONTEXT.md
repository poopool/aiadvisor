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

Backlog is split into **Delivered** (implemented) and **Pending** (pre-production / GCP).

### Delivered

| ID | Title | Acceptance Criteria | Owners |
|---|---|---|---|
| **A-P0-01** | Container Strategy | Dockerfile for API and Frontend; `docker-compose.yml` for local stack including DB. | Arch |
| **A-P0-02** | Database Schema | SQL Schema for Trades, Positions, MarketData tables (Alembic migrations). | Arch |
| **A-P0-03** | API Skeleton | FastAPI boilerplate with Health Check endpoint connected to DB. | Arch |
| **A-P1-01** | Ingestion & Technical Pipeline | Input: Tickers. Output: Price, SMA_50, SMA_200, RSI_14, ATR_14, IV_30d; persists to Data Layer. | Arch, Trader |
| **A-P1-02** | Volatility Logic Gate | IV/NATR calculation. | Trader |
| **A-P1-03** | Option Chain Fetcher | Option chain for ticker; filter 30–45 DTE. | Arch |
| **A-P1-04** | Strategy Selector | Map Technical State to Option Strategy. | Trader |
| **A-P1-05** | Strike Selection Engine | Select strikes by Delta (~0.20–0.30). | Trader |
| **A-P1-06** | LLM Synthesis Layer | Technicals + Option + News → LLM for Thesis. | Arch |
| **A-P1-07** | Market Regime Filter | SPY 200-day SMA; block Short Put in bear regimes. | Trader |
| **A-P1-08** | Expected Move Engine | 1-SD move for target expiry; strike outside range. | Trader |
| **A-P1-09** | Frontend: Approval Queue | UI table for PENDING recommendations; Approve / Reject. | Frontend |
| **A-P2-01** | Portfolio State Store | Persistent store for Active Positions (Ticker, Strike, Entry). | Arch |
| **A-P2-02** | Market Data Poller | Scheduler updates Price and Mark via Smart Polling (15 min market hours). | Arch |
| **A-P2-03** | 21 DTE Rule Monitor | Expiry − Today ≤ 21 days → ALERT. | Trader |
| **A-P2-04** | Strike Touch Monitor | Stock price vs short strike → ALERT on touch. | Trader |
| **A-P2-05** | Stop Loss Monitor | Mark ≥ 3× Entry → ALERT. | Trader |
| **A-P2-06** | Take Profit Monitor | Mark ≤ 0.5× Entry Credit → ALERT. | Trader |
| **A-P2-07** | Alert Idempotency | ALERT_SENT state per trigger; no spam. | Arch |
| **A-P2-08** | System Heartbeat | "System Online" every 4h; data freshness check; optional webhooks. | Arch |
| **A-P2-09** | Frontend: Watchtower | Dashboard for ActivePositions; Red/Green stop and profit indicators. | Frontend |
| **A-P3-01** | S&P 500 Universe Loader | Auto-fetch S&P 500 constituents (e.g. Wikipedia). | Arch |
| **A-P3-02** | Liquidity Filter | ADV and spread filter (option-level; see A-FIX-02 for 5M/5%). | Trader |
| **A-P3-03** | Batch Analysis Runner | Phase 1 logic on liquid tickers; rate-limited. | Arch |
| **A-P3-04** | Macro/Event Filter | Earnings date; exclude if within trade duration. | Trader |
| **A-P3-05** | Sector Correlation Cap | Max 2 active trades per sector. | Trader |
| **A-P3-06** | Rate Limit Controller | Queuing for API calls (in-memory). | Arch |
| **A-P5-01** | Macro Calendar Provider | High-impact events (CPI, NFP, FOMC). Gate: block entries if event within MACRO_LOOKAHEAD_HOURS (48h). | Arch |
| **A-P5-02** | Externalized Strategy Config | All thresholds from config (no hardcoded RSI/Yield/etc.). | Arch |
| **A-P5-03** | Refined Entry Gates | RSI < RSI_ENTRY_THRESHOLD (40); Annualized Yield > MIN_YIELD_PCT (0.20). | Trader |
| **A-P5-04** | Income Shield (Roll Logic) | ROLL_NEEDED if (Price−Strike)/Strike > ROLL_ITM_PCT and DTE < ROLL_DTE_TRIGGER (14). | Trader |
| **A-P5-05** | Sector Value Exposure | Track capital_deployed; block if sector sum > MAX_SECTOR_ALLOCATION (70%). | Arch |
| **A-FIX-10** | Robust Watchman Scheduler | APScheduler; exceptions logged; no zombie loop. | Arch |
| **A-FIX-11** | Remove Silent Mock Fallbacks | DataFetchError instead of fake data on NotImplementedError. | Dev |
| **A-FIX-12** | Price Slippage & Bid/Ask | Bid for credit est, Ask for buy-to-close. | Trader |
| **A-FIX-13** | Recommendation Idempotency | Existing PENDING same Ticker/Strategy/Expiry → return existing ID. | Dev |
| **A-FIX-14** | JSON Serialization Precision | Decimals as strings in JSON. | Dev |
| **A-P7-01** | Term Structure Interpolation | IV at target DTE (not generic IV_30d); IV/NATR uses IV_Target_Expiry. | Quant |
| **A-P7-02** | Volatility Skew Gate | 25Δ Skew = IV(Put_25Δ) − IV(Call_25Δ); block Short Put if Skew > MAX_SKEW_THRESHOLD. | Quant |
| **A-UI-01** | Global Dark Mode & App Shell | Financial dark mode; Sidebar (Dashboard, Analyst, Queue, Watchtower); monospace for financial data. | Frontend |
| **A-UI-02** | The Analyst Console | Page `/analyst`: ticker search → POST /analyze; card with thesis, Greeks, safety; Add to Queue / Dismiss. | Frontend |
| **A-UI-03** | Command Center Dashboard | Home: System Health (heartbeat), Quick Stats, Batch Trigger. | Frontend |
| **A-UI-04** | Enhanced Data Tables | Status badges; expandable rows (thesis, risk rules); copy contract ID. | Frontend |
| **A-UI-05** | System Notifications (Toasts) | Success/Error toasts on Approve, Reject, Analysis, heartbeat failure. | Frontend |
| **A-P9-01** | Manual Position Management | POST /positions/manual, DELETE /positions/{id}; UI Add Manual Position + Delete per row with confirm. | Arch, Frontend |
| **A-FIX-15** | Efficient Watchman Scheduling | _watchman_job exits early when market closed (is_market_hours). | Arch |
| **A-FIX-01** | Fix IV/NATR Logic | Ratio = IV_30d / ((ATR_14/Close*100)*sqrt(252)); gate > 1.0. | Trader |
| **A-FIX-02** | Refine Liquidity Gates | Stock ADV > 5M; Option (Ask−Bid)/Bid < 0.05 (5%). | Trader |
| **A-FIX-03** | Hard Earnings Exclusion | NO_TRADE if earnings between Today and Expiry. | Trader |
| **A-FIX-04** | Ticker-Level Trend Filter | Block Short Put if Ticker_Price < Ticker_SMA_50. | Trader |
| **A-FIX-05** | UI: Stale Thesis Warning | "THESIS STALE" if Live_Price < Rec_Price×0.95 or Live_Credit < Rec_Credit×0.90. | Frontend |
| **A-FIX-06** | High-Freq Active Polling | Watchman every 15 min during market hours. | Arch |
| **A-FIX-07** | Schema: Rolling Lineage | parent_position_id, root_position_id, roll_count, realized_pnl_pre_roll. | Arch |
| **A-FIX-08** | Abstract Data Provider | MarketDataProvider interface; no hardcoded polygon in core. | Arch |
| **A-FIX-09** | Decimal Precision Check | Price/Greek columns DECIMAL(10,4) or higher. | Arch |
| **A-P11-01** | Backend P&L Engine | market_value, unrealized_pnl, return_pct (Short: profit when Entry > Mark). | Arch |
| **A-P11-02** | Live Greeks Ingestion | get_greeks_for_position; greeks JSONB on ActivePosition. | Quant |
| **A-P11-03** | Watchtower UI Redesign | Card layout: Ticker+Strategy; Market Value + Total Return % (green/red). | Frontend |
| **A-P11-04** | Portfolio Summary Header | Total Market Value, Total Daily P&L, Total Unrealized P&L. | Frontend |
| **A-P11-05** | Position Detail Expansion | Expand card: Avg Cost, Mark, Today’s Return, Total Return, Diversity %, Greeks. | Frontend |
| **A-OPS-06** | Force Market Updates & Status Banner | FORCE_MARKET_UPDATES config; _watchman_job guard; GET /heartbeat market_status (OPEN/CLOSED/FORCED); frontend banners. | Arch, Frontend |
| **A-OPS-07** | Configurable Watchman Interval | WATCHMAN_INTERVAL_MINUTES in config; scheduler uses it (default 15). | Arch |
| **A-FIX-16** | Implement Polygon Provider | get_quote in PolygonMarketDataProvider (last trade + prev close fallback). | Dev |
| **A-OPS-08** | Debug Logging Mode | BACKEND_DEBUG; logging level DEBUG/INFO; debug logs in watchman job and watchman.py. | Arch |
| **A-FIX-17** | Bind Config & Schema | Position schema: market_value, unrealized_pnl, return_pct, greeks; frontend type aligned. | Arch |
| **A-OPS-09** | Provider Configuration | DATA_PROVIDER, TRADIER_API_TOKEN; get_market_data_provider factory; mock overrides. | Arch |
| **A-FIX-18** | Tradier: Watchman (Quotes) | TradierMarketDataProvider.get_quote → (underlying_price, option_mark). | Dev |
| **A-FIX-19** | Tradier: Analyst (Chains & History) | get_daily_bars, get_option_chain; map to latest bar and chain schema. | Dev |
| **A-FIX-20** | Polygon: Analyst Gap Fill | get_daily_bars and get_option_chain in PolygonMarketDataProvider. | Dev |
| **A-FIX-21** | Greeks Normalization | Both providers return delta, theta, gamma; Watchtower shows Greeks. | Quant |

### Pending

*Pre-Production & GCP: secure, scalable, observable.*

| ID | Title | Acceptance Criteria | Owners |
|---|---|---|---|
| **A-OPS-01** | Redis Rate Limiter | Replace in-memory limiter with Redis Token Bucket; shared across replicas (Cloud Run). | Arch |
| **A-OPS-02** | API Authentication | API Key or Basic Auth for all POST endpoints; 401 Unauthorized when invalid. | Security |
| **A-OPS-03** | External Secrets Management | No hardcoded passwords in docker-compose; secrets from Environment Variables only. | Ops |
| **A-OPS-04** | Structured Logging | JSON-structured logger (e.g. structlog): severity, timestamp, correlation_id for Cloud Logging. | Ops |
| **A-OPS-05** | Dedicated Worker Service | Watchman in separate worker entrypoint; API and Worker as distinct services in docker-compose and Cloud Run. | Arch |

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