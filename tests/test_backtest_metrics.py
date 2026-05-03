"""Tests for backtest.metrics."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from backtest.metrics import summarize


def _equity_curve(values: list[float], freq: str = "15min") -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(values), freq=freq, tz="UTC")
    return pd.Series(values, index=idx)


def test_metrics_flat_curve_no_trades():
    eq = _equity_curve([1000.0] * 10)
    m = summarize(eq, trades=[])
    assert m.total_return_pct == 0.0
    assert m.sharpe == 0.0
    assert m.max_drawdown_pct == 0.0
    assert m.profit_factor == 0.0
    assert m.num_trades == 0


def test_metrics_max_drawdown_basic():
    # 100 -> 120 -> 90 (drawdown 25% from peak)
    eq = _equity_curve([100, 110, 120, 110, 100, 90, 95, 100])
    m = summarize(eq, trades=[])
    assert m.max_drawdown_pct == pytest.approx(-25.0, rel=1e-6)


def test_metrics_profit_factor_and_win_rate():
    trades = [
        {"pnl": 10.0, "risk": 5.0},
        {"pnl": -5.0, "risk": 5.0},
        {"pnl": 20.0, "risk": 5.0},
        {"pnl": -5.0, "risk": 5.0},
    ]
    # Equity bumps proportionally so the curve has data.
    eq = _equity_curve([1000, 1010, 1005, 1025, 1020])
    m = summarize(eq, trades)
    assert m.num_trades == 4
    assert m.num_winners == 2
    assert m.num_losers == 2
    assert m.win_rate_pct == 50.0
    assert m.profit_factor == pytest.approx(30.0 / 10.0)
    assert m.expectancy == pytest.approx((10 - 5 + 20 - 5) / 4)
    # Avg R = mean(pnl/risk) = (2 - 1 + 4 - 1) / 4 = 1.0
    assert m.avg_r == pytest.approx(1.0)


def test_metrics_profit_factor_inf_when_no_losers():
    trades = [{"pnl": 5.0}, {"pnl": 10.0}]
    eq = _equity_curve([1000, 1005, 1015])
    m = summarize(eq, trades)
    assert math.isinf(m.profit_factor)


def test_metrics_cagr_positive_growth():
    # 1 year of 15-min bars (~35040), but for sanity just span 1 year between
    # first and last index points.
    idx = pd.date_range("2024-01-01", "2025-01-01", freq="D", tz="UTC")
    values = [1000.0 * (1.5 ** (i / len(idx))) for i in range(len(idx))]
    eq = pd.Series(values, index=idx)
    m = summarize(eq, trades=[])
    # Roughly 50% in one year.
    assert m.cagr_pct == pytest.approx(50.0, abs=2.0)
