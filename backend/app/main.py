# AI Advisor Bot — FastAPI Entrypoint (Phase 0–2)
# GET /health, POST /analyze/{ticker}, Approval/Positions, Watchman scheduler

import asyncio
import sys
from pathlib import Path

# Ensure repo root is on path so "database" package is importable when running from backend/
_repo_root = Path(__file__).resolve().parent.parent.parent
if _repo_root.exists() and str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
import json

from decimal import Decimal
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import and_, text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.analysis import run_analysis
from app.watchman import run_watchman_cycle, get_heartbeat_message
from app.batch_analysis import run_batch_analysis
from app.services.ingestion import fetch_market_data, persist_market_data

# Database (import after path fix)
from database.session import get_engine, get_session_factory, init_db
from database.models import TradeRecommendation, ActivePosition

# A-FIX-14: JSON serialization — Decimal as string to prevent IEEE 754 precision loss
def _decimal_serializer(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class DecimalJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, default=_decimal_serializer, ensure_ascii=False).encode("utf-8")


app = FastAPI(
    title="AI Advisor Bot API",
    description="Options analytics engine — Phase 0 & 1",
    version="0.1.0",
    default_response_class=DecimalJSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = get_engine(settings.database_url)
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = get_session_factory(_get_engine())
    return _session_factory


async def get_db() -> AsyncSession:
    async with _get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _post_json_to_webhook(url: str, payload: dict) -> None:
    """A-P2-08: POST JSON to webhook (sync, run in thread). Swallows errors."""
    import json
    import urllib.request
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass  # delivery best-effort; avoid crashing Watchman


# A-FIX-10: Robust Watchman Scheduler — APScheduler; handles exceptions, logs failures, no zombie loop
_watchman_scheduler = None
_last_heartbeat_time: float = 0.0


async def _watchman_job():
    """Single Watchman cycle + optional 4h heartbeat. Exceptions logged and re-raised so scheduler can retry."""
    import time
    global _last_heartbeat_time
    from app.watchman import DataFetchError
    from app.market_hours import is_market_hours
    session_factory = _get_session_factory()
    try:
        async with session_factory() as session:
            triggered = await run_watchman_cycle(session, mock=settings.ingestion_mock_mode)
            await session.commit()
            if triggered and getattr(settings, "alert_webhook_url", ""):
                await asyncio.to_thread(
                    _post_json_to_webhook,
                    settings.alert_webhook_url,
                    {"alerts": triggered, "source": "watchman"},
                )
    except DataFetchError as e:
        # A-FIX-11: Explicit data fetch failure — log, do not fail open
        import logging
        logging.getLogger("watchman").warning("Watchman cycle data fetch failed: %s", e)
    except Exception as e:
        import logging
        logging.getLogger("watchman").exception("Watchman cycle failed: %s", e)
        raise  # let scheduler see failure

    now = time.monotonic()
    if now - _last_heartbeat_time >= 4 * 3600:
        _last_heartbeat_time = now
        if getattr(settings, "heartbeat_webhook_url", ""):
            await asyncio.to_thread(_post_json_to_webhook, settings.heartbeat_webhook_url, get_heartbeat_message())


def _schedule_watchman():
    """A-FIX-10: Start APScheduler with Watchman job (15 min). Handles exceptions, logs failures, no zombie loop."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    global _watchman_scheduler
    _watchman_scheduler = AsyncIOScheduler()
    # AsyncIOScheduler will call _watchman_job() and await the coroutine
    _watchman_scheduler.add_job(
        _watchman_job,
        "interval",
        minutes=15,
        id="watchman_cycle",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=60),
    )
    _watchman_scheduler.start()


@app.on_event("startup")
async def startup():
    await init_db(_get_engine())
    _schedule_watchman()


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """Returns API and DB status."""
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e!s}"
    return {
        "status": "ok",
        "database": db_status,
        "mock_ingestion": settings.ingestion_mock_mode,
    }


@app.post("/analyze/{ticker}")
async def analyze(
    ticker: str,
    use_llm: bool = Query(default=settings.use_llm),
    db: AsyncSession = Depends(get_db),
):
    """
    Run the analysis pipeline for a single ticker.
    Fetches market data, persists to Data Layer (§2.2), then runs analysis.
    Returns the Trade Recommendation schema (§6.1).
    A-FIX-13: Idempotent — returns existing PENDING rec if same Ticker/Strategy/Expiry exists.
    """
    if not ticker or not ticker.strip():
        raise HTTPException(status_code=400, detail="ticker is required")
    ticker = ticker.strip().upper()

    mock = settings.ingestion_mock_mode
    # §2.2: Fetch then persist to Data Layer before analysis
    market_data = fetch_market_data(ticker, mock=mock)
    await persist_market_data(db, ticker, market_data["latest"])
    result = run_analysis(ticker, db, mock_ingestion=mock, use_llm=use_llm, market_data_result=market_data)

    rec_payload = result.get("recommendation")
    # A-FIX-03: NO_TRADE (e.g. earnings) — do not persist; also skip Strategy=NONE (failed gates)
    if result.get("no_trade") or rec_payload is None or rec_payload.get("strategy") == "NONE":
        return result

    # A-P5-01: Macro calendar gate — block new entries if high-impact event within lookahead
    from app.services.macro_calendar import macro_event_gate_blocked, get_macro_calendar_provider
    if macro_event_gate_blocked(
        settings.macro_lookahead_hours,
        get_macro_calendar_provider(mock=mock, api_key=getattr(settings, "trading_economics_api_key", "") or ""),
    ):
        return {
            "ticker": result["ticker"],
            "timestamp": result["timestamp"],
            "regime": result["regime"],
            "no_trade": True,
            "reason": "NO_TRADE: High-impact macro event within lookahead window.",
            "analysis": result.get("analysis", {}),
            "recommendation": None,
        }

    # A-FIX-13: Recommendation idempotency — return existing PENDING if same Ticker/Strategy/Expiry
    existing = await db.execute(
        select(TradeRecommendation).where(
            and_(
                TradeRecommendation.ticker == ticker,
                TradeRecommendation.strategy == rec_payload["strategy"],
                TradeRecommendation.expiry == date.fromisoformat(rec_payload["expiry"]),
                TradeRecommendation.status == "PENDING",
            )
        ).order_by(TradeRecommendation.created_at.desc()).limit(1)
    )
    existing_rec = existing.scalar_one_or_none()
    if existing_rec:
        # Return existing recommendation payload (reconstruct from calculated_metrics)
        metrics = existing_rec.calculated_metrics or {}
        return {
            "ticker": existing_rec.ticker,
            "timestamp": metrics.get("timestamp", ""),
            "regime": metrics.get("regime", ""),
            "analysis": metrics.get("analysis", {}),
            "recommendation": metrics.get("recommendation", {}),
            "existing_recommendation_id": str(existing_rec.id),
        }

    # A-P5-05: Sector value exposure — block if sector would exceed MAX_SECTOR_ALLOCATION
    sector = (result.get("analysis") or {}).get("sector") or "Unknown"
    new_capital = float(rec_payload.get("strike", 0)) * 100 * 1  # strike * 100 * contracts
    from app.services.universe import sector_value_exposure_allowed
    if not await sector_value_exposure_allowed(
        db, sector, new_capital, getattr(settings, "max_sector_allocation_pct", 0.70)
    ):
        return {
            "ticker": result["ticker"],
            "timestamp": result["timestamp"],
            "regime": result["regime"],
            "no_trade": True,
            "reason": "NO_TRADE: Sector value exposure would exceed max allocation.",
            "analysis": result.get("analysis", {}),
            "recommendation": None,
        }

    # Persist to TradeRecommendation for audit
    from database.models import TradeRecommendation

    rec = TradeRecommendation(
        id=uuid4(),
        ticker=result["ticker"],
        strategy=rec_payload["strategy"],
        strike=Decimal(str(rec_payload["strike"])),
        expiry=date.fromisoformat(rec_payload["expiry"]),
        status="PENDING",
        calculated_metrics={
            "timestamp": result["timestamp"],
            "regime": result["regime"],
            "analysis": result["analysis"],
            "recommendation": rec_payload,
        },
    )
    db.add(rec)
    await db.flush()

    return result


def _thesis_stale(live_price: float, rec_price: float, live_credit: float, rec_credit: float) -> bool:
    """A-FIX-05: THESIS STALE if Live_Price < Rec_Price*0.95 OR Live_Credit < Rec_Credit*0.90."""
    if rec_price <= 0 and rec_credit <= 0:
        return False
    if rec_price > 0 and live_price < rec_price * 0.95:
        return True
    if rec_credit > 0 and live_credit < rec_credit * 0.90:
        return True
    return False


@app.get("/recommendations")
async def list_recommendations(
    status: str | None = Query(None, description="Filter by status: PENDING, APPROVED, REJECTED"),
    check_stale: bool = Query(False, description="A-FIX-05: Include live_price, live_credit, thesis_stale"),
    db: AsyncSession = Depends(get_db),
):
    """List trade recommendations for the Approval Queue (default: PENDING)."""
    q = select(TradeRecommendation).order_by(TradeRecommendation.created_at.desc())
    if status:
        q = q.where(TradeRecommendation.status == status.upper())
    else:
        q = q.where(TradeRecommendation.status == "PENDING")
    result = await db.execute(q)
    rows = result.scalars().all()
    out = []
    for r in rows:
        item = {
            "id": str(r.id),
            "ticker": r.ticker,
            "strategy": r.strategy,
            "strike": float(r.strike),
            "expiry": r.expiry.isoformat(),
            "status": r.status,
            "calculated_metrics": r.calculated_metrics,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        if check_stale and r.calculated_metrics:
            rec_analysis = (r.calculated_metrics or {}).get("analysis") or {}
            rec_rec = (r.calculated_metrics or {}).get("recommendation") or {}
            rec_price = float(rec_analysis.get("price") or 0)
            rec_credit = float(rec_rec.get("credit_est") or 0)
            # TODO: fetch live quote from provider; for now use rec values (mock)
            live_price = rec_price
            live_credit = rec_credit
            item["live_price"] = live_price
            item["live_credit"] = live_credit
            item["thesis_stale"] = _thesis_stale(live_price, rec_price, live_credit, rec_credit)
        out.append(item)
    return out


@app.post("/recommendations/{recommendation_id}/approve")
async def approve_recommendation(
    recommendation_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Approve a recommendation: set status to APPROVED and create ActivePosition (move to Monitor)."""
    result = await db.execute(select(TradeRecommendation).where(TradeRecommendation.id == recommendation_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if rec.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Recommendation status is {rec.status}, not PENDING")
    metrics = rec.calculated_metrics or {}
    rec_analysis = metrics.get("analysis") or {}
    rec_rec = metrics.get("recommendation") or {}
    entry_price = Decimal(str(rec_rec.get("credit_est", 3.5)))
    stop_loss = entry_price * Decimal("3")  # 3x credit
    take_profit = entry_price * Decimal("0.5")  # 50% profit
    expiry_date = rec.expiry
    force_close = expiry_date - timedelta(days=21)
    if force_close < date.today():
        force_close = date.today()
    # A-P5-05: Track capital_deployed and sector for sector value exposure
    contracts = 1
    capital_deployed = float(rec.strike) * 100 * contracts
    sector = (rec_analysis.get("sector") or "Unknown")
    position = ActivePosition(
        id=uuid4(),
        ticker=rec.ticker,
        status="OPEN",
        lifecycle_stage="MONITORING",
        entry_data={
            "strategy": rec.strategy,
            "short_strike": float(rec.strike),
            "expiry_date": expiry_date.isoformat(),
            "entry_price": float(entry_price),
            "entry_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "contracts": contracts,
            "capital_deployed": capital_deployed,
            "sector": sector,
        },
        risk_rules={
            "stop_loss_price": float(stop_loss),
            "take_profit_price": float(take_profit),
            "max_dte_hold": 21,
            "force_close_date": force_close.isoformat(),
        },
        last_heartbeat=None,
    )
    db.add(position)
    rec.status = "APPROVED"
    await db.flush()
    return {"ok": True, "recommendation_id": str(rec.id), "position_id": str(position.id)}


@app.post("/recommendations/{recommendation_id}/reject")
async def reject_recommendation(
    recommendation_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Reject a recommendation: set status to REJECTED."""
    result = await db.execute(select(TradeRecommendation).where(TradeRecommendation.id == recommendation_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if rec.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Recommendation status is {rec.status}, not PENDING")
    rec.status = "REJECTED"
    await db.flush()
    return {"ok": True, "recommendation_id": str(rec.id)}


@app.get("/positions")
async def list_positions(
    db: AsyncSession = Depends(get_db),
):
    """List active positions for the Watchtower (lifecycle_stage != CLOSED)."""
    q = select(ActivePosition).where(ActivePosition.lifecycle_stage != "CLOSED").order_by(ActivePosition.created_at.desc())
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "ticker": p.ticker,
            "status": p.status,
            "lifecycle_stage": p.lifecycle_stage,
            "entry_data": p.entry_data,
            "risk_rules": p.risk_rules,
            "last_heartbeat": p.last_heartbeat,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in rows
    ]


@app.get("/heartbeat")
async def heartbeat():
    """A-P2-08: System heartbeat (also used by Watchman every 4h)."""
    return get_heartbeat_message()


@app.post("/analyze/batch")
async def analyze_batch(
    db: AsyncSession = Depends(get_db),
):
    """A-P3-03: Run analysis on liquid universe (S&P 500, rate-limited). Returns list of §6.1 recommendations. A-P5-01: Macro gate applied."""
    from app.services.macro_calendar import macro_event_gate_blocked, get_macro_calendar_provider
    from app.services.universe import sector_value_exposure_allowed

    if macro_event_gate_blocked(
        settings.macro_lookahead_hours,
        get_macro_calendar_provider(mock=settings.ingestion_mock_mode, api_key=getattr(settings, "trading_economics_api_key", "") or ""),
    ):
        return {"blocked": True, "reason": "High-impact macro event within lookahead.", "results": []}

    results = await run_batch_analysis(db, mock_ingestion=settings.ingestion_mock_mode, max_tickers=10)
    for rec in results:
        r = rec.get("recommendation") or {}
        if not r or r.get("strategy") == "NONE":
            continue
        sector = (rec.get("analysis") or {}).get("sector") or "Unknown"
        new_capital = float(r.get("strike", 0)) * 100 * 1
        if not await sector_value_exposure_allowed(db, sector, new_capital, getattr(settings, "max_sector_allocation_pct", 0.70)):
            continue
        from database.models import TradeRecommendation
        rec_row = TradeRecommendation(
            id=uuid4(),
            ticker=rec["ticker"],
            strategy=r.get("strategy", "SHORT_PUT"),
            strike=Decimal(str(r.get("strike", 0))),
            expiry=date.fromisoformat(r.get("expiry", date.today().isoformat())),
            status="PENDING",
            calculated_metrics={"timestamp": rec.get("timestamp"), "regime": rec.get("regime"), "analysis": rec.get("analysis"), "recommendation": r},
        )
        db.add(rec_row)
    await db.flush()
    return results
