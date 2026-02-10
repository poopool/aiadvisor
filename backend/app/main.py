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

from fastapi import FastAPI, HTTPException, Depends, Query
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.analysis import run_analysis
from app.watchman import run_watchman_cycle, get_heartbeat_message
from app.batch_analysis import run_batch_analysis

# Database (import after path fix)
from database.session import get_engine, get_session_factory, init_db
from database.models import TradeRecommendation, ActivePosition

app = FastAPI(
    title="AI Advisor Bot API",
    description="Options analytics engine — Phase 0 & 1",
    version="0.1.0",
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


@app.on_event("startup")
async def startup():
    await init_db(_get_engine())
    asyncio.create_task(_watchman_loop())


async def _watchman_loop():
    """A-P2-02 / A-FIX-06: Poll ActivePositions every 15 min during market hours, else hourly; heartbeat every 4h."""
    from app.market_hours import is_market_hours
    await asyncio.sleep(60)  # let API settle
    session_factory = _get_session_factory()
    heartbeat_interval = 4 * 3600  # 4 hours
    interval_market = 15 * 60   # 15 minutes during market hours
    interval_off = 3600         # 1 hour outside market hours
    last_heartbeat = 0.0
    while True:
        try:
            async with session_factory() as session:
                triggered = await run_watchman_cycle(session, mock=settings.ingestion_mock_mode)
                await session.commit()
                if triggered:
                    pass  # TODO: send to human (email/webhook)
        except Exception:
            pass  # log and continue
        cycle_interval = interval_market if is_market_hours() else interval_off
        await asyncio.sleep(cycle_interval)
        last_heartbeat += cycle_interval
        if last_heartbeat >= heartbeat_interval:
            last_heartbeat = 0.0
            _ = get_heartbeat_message()  # TODO: send heartbeat to human


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
    db: AsyncSession = Depends(get_db),
):
    """
    Run the analysis pipeline for a single ticker.
    Returns the Trade Recommendation schema (§6.1).
    """
    if not ticker or not ticker.strip():
        raise HTTPException(status_code=400, detail="ticker is required")
    ticker = ticker.strip().upper()

    mock = settings.ingestion_mock_mode
    result = run_analysis(ticker, mock_ingestion=mock)

    # A-FIX-03: NO_TRADE (e.g. earnings) — do not persist
    if result.get("no_trade") or result.get("recommendation") is None:
        return result

    # Persist to TradeRecommendation for audit
    from database.models import TradeRecommendation

    rec = TradeRecommendation(
        id=uuid4(),
        ticker=result["ticker"],
        strategy=result["recommendation"]["strategy"],
        strike=Decimal(str(result["recommendation"]["strike"])),
        expiry=date.fromisoformat(result["recommendation"]["expiry"]),
        status="PENDING",
        calculated_metrics={
            "timestamp": result["timestamp"],
            "regime": result["regime"],
            "analysis": result["analysis"],
            "recommendation": result["recommendation"],
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
            "contracts": 1,
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
    """A-P3-03: Run analysis on liquid universe (S&P 500, rate-limited). Returns list of §6.1 recommendations."""
    results = await run_batch_analysis(mock_ingestion=settings.ingestion_mock_mode, max_tickers=10)
    for rec in results:
        from database.models import TradeRecommendation
        r = rec.get("recommendation") or {}
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
