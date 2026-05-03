"""Unit tests for tp_sl_calculator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tp_sl_calculator import calculate_dynamic_tp_sl


def _make_df(prices, length=60):
    rng = np.random.default_rng(0)
    closes = np.linspace(prices[0], prices[-1], length)
    df = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=length, freq="15min", tz="UTC"),
        "open": closes,
        "high": closes * (1 + rng.uniform(0, 0.005, size=length)),
        "low": closes * (1 - rng.uniform(0, 0.005, size=length)),
        "close": closes,
        "volume": rng.uniform(100, 1000, size=length),
    })
    return df


def test_buy_levels_have_minimum_rr_ratio():
    df = _make_df([100, 105])
    levels = calculate_dynamic_tp_sl(df, current_price=105.0, signal_type="BUY")
    # Either we achieved >=1.5 R:R, or we documented why we couldn't.
    assert levels["rr_ratio"] >= 1.5 - 1e-6
    assert levels["tp"] > 105.0
    assert levels["sl"] < 105.0


def test_strong_buy_levels_have_minimum_rr_ratio():
    df = _make_df([100, 105])
    levels = calculate_dynamic_tp_sl(df, current_price=105.0, signal_type="STRONG_BUY")
    assert levels["rr_ratio"] >= 1.5 - 1e-6


def test_rr_ratio_matches_tp_sl_after_adjustment():
    """Bug 1.8 regression: rr_ratio is computed from final TP/SL, not hardcoded."""
    df = _make_df([100, 102])
    levels = calculate_dynamic_tp_sl(df, current_price=102.0, signal_type="BUY")
    risk = 102.0 - levels["sl"]
    reward = levels["tp"] - 102.0
    expected = round(reward / risk, 2) if risk > 0 else 1.0
    assert levels["rr_ratio"] == pytest.approx(expected, rel=1e-2)


def test_fallback_when_dataframe_invalid():
    df = pd.DataFrame()
    levels = calculate_dynamic_tp_sl(df, current_price=100.0, signal_type="BUY")
    assert "tp" in levels and "sl" in levels and levels["tp"] > 100.0 and levels["sl"] < 100.0
