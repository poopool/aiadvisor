# AI Advisor Bot — Technical indicators from daily OHLCV bars
# Used by Polygon and Tradier providers to compute latest { close, sma_50, sma_200, atr_14, rsi_14 }.

from datetime import date
from decimal import Decimal
from typing import Any


def _to_decimal(v: Any) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def compute_sma(closes: list[Decimal], period: int) -> Decimal | None:
    """SMA over the last `period` closes. Returns None if insufficient data."""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def compute_atr_14(bars: list[dict]) -> Decimal | None:
    """ATR(14) from bars with keys h, l, c (high, low, close). Uses last 15 bars (14 ranges)."""
    if len(bars) < 15:
        return None
    trs = []
    for i in range(1, len(bars)):
        h = _to_decimal(bars[-i].get("h") or bars[-i].get("high") or 0)
        l = _to_decimal(bars[-i].get("l") or bars[-i].get("low") or 0)
        prev_c = _to_decimal(bars[-(i + 1)].get("c") or bars[-(i + 1)].get("close") or 0)
        tr = max(
            h - l,
            abs(h - prev_c),
            abs(l - prev_c),
        )
        trs.append(tr)
        if len(trs) >= 14:
            break
    if len(trs) < 14:
        return None
    return sum(trs) / len(trs)


def compute_rsi_14(closes: list[Decimal]) -> Decimal | None:
    """RSI(14) from close prices. Needs at least 15 closes."""
    if len(closes) < 15:
        return None
    gains, losses = [], []
    for i in range(len(closes) - 14, len(closes)):
        ch = closes[i] - closes[i - 1]
        if ch > 0:
            gains.append(ch)
            losses.append(Decimal("0"))
        else:
            gains.append(Decimal("0"))
            losses.append(-ch)
    avg_gain = sum(gains) / 14
    avg_loss = sum(losses) / 14
    if avg_loss == 0:
        return Decimal("100")
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return Decimal(str(round(rsi, 2)))


def bars_to_latest(
    bars: list[dict],
    *,
    default_iv_30d: Decimal = Decimal("0.25"),
    bar_date_key: str = "date",
) -> dict[str, Any]:
    """
    Build 'latest' dict from list of bars. Each bar: { date, open?, high/h, low/l, close/c, volume? }.
    Returns { date, close, sma_50, sma_200, atr_14, rsi_14, iv_30d }.
    """
    if not bars:
        return {}
    # Normalize keys (Polygon: o,h,l,c; Tradier: open, high, low, close)
    normalized = []
    for b in bars:
        c = b.get("c") or b.get("close")
        if c is None:
            continue
        normalized.append({
            "date": b.get("date") or b.get("t"),
            "o": b.get("o") or b.get("open"),
            "h": b.get("h") or b.get("high"),
            "l": b.get("l") or b.get("low"),
            "c": _to_decimal(c),
        })
    if not normalized:
        return {}
    closes = [x["c"] for x in normalized]
    last = normalized[-1]
    bar_date = last.get("date")
    if isinstance(bar_date, (int, float)):
        from datetime import datetime
        bar_date = datetime.utcfromtimestamp(bar_date / 1000.0 if bar_date > 1e10 else bar_date).date().isoformat()
    elif hasattr(bar_date, "isoformat"):
        bar_date = bar_date.isoformat()
    elif bar_date is None:
        bar_date = date.today().isoformat()

    sma_50 = compute_sma(closes, 50)
    sma_200 = compute_sma(closes, 200)
    atr_14 = compute_atr_14(normalized)
    rsi_14 = compute_rsi_14(closes)

    return {
        "date": bar_date,
        "close": last["c"],
        "sma_50": sma_50,
        "sma_200": sma_200,
        "atr_14": atr_14 or Decimal("0"),
        "rsi_14": rsi_14 or Decimal("50"),
        "iv_30d": default_iv_30d,
    }
