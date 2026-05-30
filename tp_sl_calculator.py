"""
Dynamic TP/SL Calculator.

Shared module for consistent TP/SL calculation across screener and signal
generator. Pure-function: takes a DataFrame and returns levels.
"""

from __future__ import annotations

import logging
from typing import TypedDict

import pandas_ta_compat as ta
from config import AGGRESSIVE_TP_MULTIPLIER, TRADING_MODE

logger = logging.getLogger(__name__)


class Levels(TypedDict):
    tp: float
    sl: float
    rr_ratio: float
    tp_pct: float
    sl_pct: float


_MIN_RR = 1.5


def _round_levels(tp: float, sl: float, current_price: float, is_bullish: bool) -> Levels:
    if TRADING_MODE == "aggressive" and AGGRESSIVE_TP_MULTIPLIER > 1:
        # Aggressive v1: keep SL unchanged, extend only reward distance.
        # This lets winners run longer while preserving the original risk.
        reward = abs(tp - current_price) * AGGRESSIVE_TP_MULTIPLIER
        tp = current_price + reward if is_bullish else current_price - reward

    if is_bullish:
        tp_pct = ((tp - current_price) / current_price) * 100
        sl_pct = ((current_price - sl) / current_price) * 100
    else:
        tp_pct = ((current_price - tp) / current_price) * 100
        sl_pct = ((sl - current_price) / current_price) * 100

    risk = abs(current_price - sl)
    reward = abs(tp - current_price)
    rr_ratio = (reward / risk) if risk > 0 else 1.0

    return {
        "tp": round(float(tp), 6),
        "sl": round(float(sl), 6),
        "rr_ratio": round(float(rr_ratio), 2),
        "tp_pct": round(float(tp_pct), 2),
        "sl_pct": round(float(sl_pct), 2),
    }


def calculate_dynamic_tp_sl(df, current_price: float, signal_type: str = "BUY") -> Levels:
    """Calculate dynamic TP/SL based on technical levels.

    Uses the closed candle (``iloc[-2]``) for indicators to avoid repainting
    against the still-forming candle.
    """
    try:
        # Use closed candle for indicator snapshots; fall back to last when
        # only one candle is available.
        idx = -2 if len(df) >= 2 else -1

        # Recent extremes excluding the in-progress candle.
        closed_df = df.iloc[:idx] if idx == -2 else df
        recent_high = float(closed_df["high"].tail(20).max())
        recent_low = float(closed_df["low"].tail(20).min())

        bb_upper = (
            float(df["bb_upper"].iloc[idx])
            if "bb_upper" in df.columns
            else current_price * 1.02
        )
        bb_lower = (
            float(df["bb_lower"].iloc[idx])
            if "bb_lower" in df.columns
            else current_price * 0.98
        )

        atr_series = ta.atr(df["high"], df["low"], df["close"], length=14)
        atr_val = float(atr_series.iloc[idx]) if atr_series is not None else current_price * 0.01
        if atr_val != atr_val or atr_val <= 0:  # NaN or non-positive
            atr_val = current_price * 0.01

        is_bullish = signal_type in {"BUY", "STRONG_BUY"}
        is_bearish = signal_type == "SELL"

        # HOLD: use price-vs-MA bias if available.
        if not is_bullish and not is_bearish:
            ma_20 = float(df["ma_20"].iloc[idx]) if "ma_20" in df.columns else current_price
            is_bullish = current_price >= ma_20  # tie -> bullish bias

        if is_bullish:
            # TP: prefer nearest technical resistance, but enforce ATR minimum
            tp_candidates = [x for x in (recent_high, bb_upper) if x > current_price]
            tp = min(tp_candidates) if tp_candidates else current_price + (atr_val * 2)
            # ATR floor so we don't get 0.1% TPs in ranging markets
            min_tp = current_price + (atr_val * 2)
            if tp < min_tp:
                tp = min_tp

            # SL: prefer nearest technical support, but enforce ATR minimum
            sl_candidates = [x for x in (recent_low, bb_lower) if x < current_price]
            sl = max(sl_candidates) if sl_candidates else current_price - atr_val
            # ATR floor — don't let SL sit inside noise
            min_sl = current_price - (atr_val * 1.5)
            if sl > min_sl:
                sl = min_sl

            risk = current_price - sl
            reward = tp - current_price

            if risk <= 0 or reward <= 0:
                tp = current_price * 1.05
                sl = current_price * 0.97
                risk = current_price - sl
                reward = tp - current_price

            rr_ratio = reward / risk
            if rr_ratio < _MIN_RR:
                # Try tightening SL first to achieve target R:R.
                required_risk = reward / _MIN_RR
                proposed_sl = current_price - required_risk
                min_sl = recent_low * 0.98 if recent_low > 0 else proposed_sl
                if proposed_sl >= min_sl:
                    sl = proposed_sl
                else:
                    # Tightening would cross support; widen TP instead.
                    tp = current_price + (risk * _MIN_RR)
                # Important: reuse _round_levels so rr_ratio is recomputed
                # from the *final* tp/sl rather than hardcoded.
            return _round_levels(tp, sl, current_price, True)

        # Bearish branch — used by SHORT entries.
        tp_candidates = [x for x in (recent_low, bb_lower) if x < current_price]
        tp = max(tp_candidates) if tp_candidates else current_price - (atr_val * 2)
        # ATR floor for SHORT TP
        min_tp = current_price - (atr_val * 2)
        if tp > min_tp:
            tp = min_tp

        sl_candidates = [x for x in (recent_high, bb_upper) if x > current_price]
        sl = min(sl_candidates) if sl_candidates else current_price + atr_val
        # ATR floor for SHORT SL
        min_sl = current_price + (atr_val * 1.5)
        if sl < min_sl:
            sl = min_sl

        risk = sl - current_price
        reward = current_price - tp
        if risk <= 0 or reward <= 0:
            tp = current_price * 0.95
            sl = current_price * 1.03
            risk = sl - current_price
            reward = current_price - tp

        rr_ratio = reward / risk
        if rr_ratio < _MIN_RR:
            required_risk = reward / _MIN_RR
            proposed_sl = current_price + required_risk
            max_sl = recent_high * 1.02 if recent_high > 0 else proposed_sl
            if proposed_sl <= max_sl:
                sl = proposed_sl
            else:
                tp = current_price - (risk * _MIN_RR)

        return _round_levels(tp, sl, current_price, False)

    except Exception as exc:
        logger.warning("Falling back to fixed TP/SL: %s", exc)
        if signal_type in {"BUY", "STRONG_BUY"}:
            tp = current_price * 1.05
            sl = current_price * 0.95
            return _round_levels(tp, sl, current_price, True)
        tp = current_price * 0.95
        sl = current_price * 1.05
        return _round_levels(tp, sl, current_price, False)
