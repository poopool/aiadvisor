# AI Advisor Bot — Quantitative Engine (Phase 1)
# Source of Truth: PROJECT_CONTEXT.md §4 — Deterministic Interfaces
# A-P5-02: All thresholds loaded from config; no hardcoded constants.

from decimal import Decimal
from typing import Literal

from decimal import ROUND_HALF_UP


def _get_iv_natr_min_ratio() -> Decimal:
    from app.config import settings
    return Decimal(str(getattr(settings, "iv_natr_min_ratio", 1.0)))


def _get_dte_alert_threshold() -> int:
    from app.config import settings
    return getattr(settings, "dte_alert_threshold", 21)


class QuantLaws:
    """
    Deterministic math for options analytics.
    All inputs/outputs for prices, IV, and ratios are Decimal.
    """

    @staticmethod
    def calculate_expected_move(
        price: Decimal,
        iv_30d: Decimal,
        dte: int,
    ) -> Decimal:
        """
        Expected Move (1 standard deviation) for the given DTE.
        EM = Price * IV_30d * sqrt(DTE/365)
        IV_30d must be in decimal form (e.g. 0.25 for 25%).
        """
        if price <= 0 or iv_30d < 0 or dte <= 0:
            return Decimal("0")
        # sqrt(DTE/365) with Decimal
        dte_over_365 = Decimal(dte) / Decimal("365")
        sqrt_dte = dte_over_365 ** Decimal("0.5")
        em = price * iv_30d * sqrt_dte
        return em.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def check_iv_natr_rule(
        iv_30d: Decimal,
        atr_14_daily: Decimal,
        close_price: Decimal,
        *,
        min_ratio: Decimal | None = None,
    ) -> tuple[Decimal, bool]:
        """
        A-FIX-01 (Spec Patch v1.1): Ratio = IV_30d / ((ATR_14/Close * 100) * sqrt(252)).
        Gate: Pass only if Ratio > 1.0.
        IV_30d in decimal (e.g. 0.25); denominator in same scale.
        """
        if close_price <= 0 or atr_14_daily < 0:
            return Decimal("0"), False
        # (ATR_14/Close)*100
        natr_pct = (atr_14_daily / close_price) * Decimal("100")
        if natr_pct <= 0:
            return Decimal("0"), False
        # denominator = (ATR_14/Close * 100) * sqrt(252)
        sqrt_252 = Decimal("252") ** Decimal("0.5")
        denominator = natr_pct * sqrt_252
        # IV_30d as decimal; for ratio use same scale: IV_30d / (denom/100) or iv_pct/denom
        iv_pct = iv_30d * Decimal("100")
        ratio = iv_pct / denominator
        threshold = min_ratio if min_ratio is not None else _get_iv_natr_min_ratio()
        passes = ratio > threshold
        return ratio.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), passes

    @staticmethod
    def check_21_dte(dte: int) -> Literal["OK", "ALERT"]:
        """
        The 21 DTE Law: flag any position at <= DTE_ALERT_THRESHOLD days to expiration.
        Returns "ALERT" if DTE <= threshold, else "OK".
        """
        if dte <= _get_dte_alert_threshold():
            return "ALERT"
        return "OK"
