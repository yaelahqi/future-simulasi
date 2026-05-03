"""Tests for backtest.engine.

These tests use synthetic OHLCV so they run offline (no ccxt calls).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.engine import BacktestSettings, run_backtest


def _synthetic_ohlcv(closes: list[float], freq: str = "15min") -> pd.DataFrame:
    """Build a DataFrame from a close-price series; high/low straddle close 0.2%."""
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC")
    closes_arr = np.array(closes, dtype=float)
    opens = np.concatenate([[closes_arr[0]], closes_arr[:-1]])
    highs = np.maximum(opens, closes_arr) * 1.002
    lows = np.minimum(opens, closes_arr) * 0.998
    vol = np.full(n, 1000.0)
    return pd.DataFrame({
        "timestamp": idx,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes_arr,
        "volume": vol,
    })


def test_run_backtest_smoke_returns_result():
    rng = np.random.default_rng(42)
    base = 100.0
    # Random-walk close series with mild drift.
    rets = rng.normal(loc=0.0001, scale=0.01, size=300)
    closes = (base * np.cumprod(1 + rets)).tolist()
    df = _synthetic_ohlcv(closes)

    result = run_backtest(df, BacktestSettings(initial_capital=1000.0, warmup_bars=60))
    assert result.bars_processed > 0
    assert result.initial_equity == 1000.0
    # Equity is finite & non-negative throughout.
    assert (result.equity_curve >= 0).all()
    # No trade should have NaN PnL.
    for t in result.trades:
        assert np.isfinite(t["pnl"])


def test_run_backtest_no_lookahead_signal_uses_only_past():
    """If we extend the future after a bar has been consumed, the equity
    curve up to that bar (excluding the truncated run's force-close at the
    last bar) must be identical."""
    rng = np.random.default_rng(0)
    closes = (100 * np.cumprod(1 + rng.normal(0.0001, 0.01, size=200))).tolist()
    df = _synthetic_ohlcv(closes)

    truncated = df.iloc[:150].reset_index(drop=True)
    res_truncated = run_backtest(truncated, BacktestSettings(warmup_bars=60))
    res_full = run_backtest(df, BacktestSettings(warmup_bars=60))

    # Drop the very last index of the truncated run, which gets force-closed
    # at end-of-data. Bars before that must match between runs.
    truncated_eq = res_truncated.equity_curve
    if len(truncated_eq) > 1:
        cutoff_ts = truncated_eq.index[-2]
        truncated_pre = truncated_eq.loc[:cutoff_ts]
    else:
        truncated_pre = truncated_eq

    common_index = truncated_pre.index.intersection(res_full.equity_curve.index)
    assert len(common_index) > 10  # sanity: sufficient overlap to be meaningful
    pd.testing.assert_series_equal(
        res_full.equity_curve.loc[common_index],
        truncated_pre.loc[common_index],
        check_names=False,
    )


def test_engine_respects_allow_long_short_flags():
    rng = np.random.default_rng(7)
    closes = (100 * np.cumprod(1 + rng.normal(0.0, 0.01, size=300))).tolist()
    df = _synthetic_ohlcv(closes)

    long_only = run_backtest(
        df, BacktestSettings(allow_long=True, allow_short=False, warmup_bars=60)
    )
    short_only = run_backtest(
        df, BacktestSettings(allow_long=False, allow_short=True, warmup_bars=60)
    )

    for t in long_only.trades:
        assert t["type"] == "BUY"
    for t in short_only.trades:
        assert t["type"] == "SELL"


def test_engine_raises_when_warmup_too_large():
    df = _synthetic_ohlcv([100.0] * 30)
    with pytest.raises(ValueError):
        run_backtest(df, BacktestSettings(warmup_bars=60))


def test_engine_funding_drag_reduces_equity():
    """Holding a position with positive funding drag should cost equity."""
    rng = np.random.default_rng(123)
    closes = (100 * np.cumprod(1 + rng.normal(0.0, 0.005, size=400))).tolist()
    df = _synthetic_ohlcv(closes, freq="1h")  # 1h bars so funding cycles every 8 bars

    no_fund = run_backtest(df, BacktestSettings(funding_bps_per_8h=0.0, warmup_bars=60))
    big_fund = run_backtest(df, BacktestSettings(funding_bps_per_8h=50.0, warmup_bars=60))

    # If both runs took the same trades, the funding run should be <= no-funding run.
    if no_fund.trades and big_fund.trades:
        assert big_fund.final_equity <= no_fund.final_equity
