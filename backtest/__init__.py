"""Bar-by-bar backtest harness for the future-simulasi strategy.

This module replays historical OHLCV through the same indicator + TP/SL +
fee + slippage + liquidation logic that the live paper trader uses, so the
backtest results are an honest forward-projection (not a re-implementation).

Public surface:

- :func:`backtest.engine.run_backtest` — execute a backtest given OHLCV,
  return :class:`backtest.engine.BacktestResult`.
- :func:`backtest.metrics.summarize` — compute Sharpe, Sortino, max DD,
  profit factor, expectancy, win rate from an equity curve + trade list.
- :func:`backtest.data.load_ohlcv_csv` /
  :func:`backtest.data.fetch_ohlcv_via_ccxt` — input adapters.
"""

from backtest.engine import BacktestResult, BacktestSettings, run_backtest
from backtest.metrics import Metrics, summarize

__all__ = [
    "BacktestResult",
    "BacktestSettings",
    "Metrics",
    "run_backtest",
    "summarize",
]
