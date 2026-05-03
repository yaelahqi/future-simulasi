"""Backtest performance metrics.

Computes the standard set of metrics finance reviewers ask for:
Sharpe, Sortino, max drawdown, profit factor, expectancy, win rate,
average R, total return. All metrics are computed from an equity curve
indexed by bar timestamp plus a list of closed trades.

A trade is a dict with at minimum:
``{"entry_price": float, "exit_price": float, "pnl": float,
   "type": "BUY"|"SELL", "opened_at": iso, "closed_at": iso}``
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Metrics:
    total_return_pct: float
    sharpe: float
    sortino: float
    max_drawdown_pct: float
    profit_factor: float
    expectancy: float
    win_rate_pct: float
    avg_win: float
    avg_loss: float
    avg_r: float
    num_trades: int
    num_winners: int
    num_losers: int
    initial_equity: float
    final_equity: float
    cagr_pct: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "total_return_pct": self.total_return_pct,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "max_drawdown_pct": self.max_drawdown_pct,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "win_rate_pct": self.win_rate_pct,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "avg_r": self.avg_r,
            "num_trades": self.num_trades,
            "num_winners": self.num_winners,
            "num_losers": self.num_losers,
            "initial_equity": self.initial_equity,
            "final_equity": self.final_equity,
            "cagr_pct": self.cagr_pct,
        }


def _max_drawdown_pct(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max.where(running_max > 0, other=1.0)
    return float(drawdown.min() * 100.0)


def _annualization_factor(equity: pd.Series) -> float:
    """Estimate periods-per-year from the equity-curve sampling cadence."""
    if len(equity.index) < 2:
        return 1.0
    ts = pd.DatetimeIndex(equity.index)
    deltas = ts.to_series().diff().dropna()
    if deltas.empty:
        return 1.0
    median_seconds = float(deltas.median().total_seconds())
    if median_seconds <= 0:
        return 1.0
    seconds_per_year = 365.25 * 24 * 3600
    return seconds_per_year / median_seconds


def _sharpe(returns: pd.Series, ann_factor: float) -> float:
    if returns.std(ddof=0) == 0 or returns.empty:
        return 0.0
    return float((returns.mean() / returns.std(ddof=0)) * math.sqrt(ann_factor))


def _sortino(returns: pd.Series, ann_factor: float) -> float:
    if returns.empty:
        return 0.0
    downside = returns[returns < 0]
    if downside.empty:
        return float("inf") if returns.mean() > 0 else 0.0
    denom = float(np.sqrt(np.mean(downside**2)))
    if denom == 0:
        return 0.0
    return float((returns.mean() / denom) * math.sqrt(ann_factor))


def _cagr(initial: float, final: float, equity: pd.Series) -> float:
    if initial <= 0 or final <= 0 or len(equity.index) < 2:
        return 0.0
    ts = pd.DatetimeIndex(equity.index)
    span_years = (ts[-1] - ts[0]).total_seconds() / (365.25 * 24 * 3600)
    if span_years <= 0:
        return 0.0
    return float(((final / initial) ** (1 / span_years) - 1) * 100.0)


def summarize(equity_curve: pd.Series, trades: Iterable[dict]) -> Metrics:
    """Compute Metrics from an equity curve and an iterable of closed trades."""
    trades = list(trades)
    equity_curve = equity_curve.astype(float).dropna()
    initial = float(equity_curve.iloc[0]) if not equity_curve.empty else 0.0
    final = float(equity_curve.iloc[-1]) if not equity_curve.empty else initial

    pnls = [float(t.get("pnl", 0.0)) for t in trades]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p < 0]
    gross_win = sum(winners)
    gross_loss = abs(sum(losers))

    num_trades = len(trades)
    num_winners = len(winners)
    num_losers = len(losers)
    win_rate_pct = (num_winners / num_trades * 100.0) if num_trades else 0.0
    avg_win = (gross_win / num_winners) if num_winners else 0.0
    avg_loss = (-gross_loss / num_losers) if num_losers else 0.0  # negative value
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (
        float("inf") if gross_win > 0 else 0.0
    )
    expectancy = (sum(pnls) / num_trades) if num_trades else 0.0

    # Average R: PnL normalized by trade-level risk (entry-to-SL distance) when present.
    rs: list[float] = []
    for trade in trades:
        risk = trade.get("risk")
        if risk is None or risk <= 0:
            continue
        rs.append(float(trade.get("pnl", 0.0)) / float(risk))
    avg_r = float(np.mean(rs)) if rs else 0.0

    returns = equity_curve.pct_change().dropna()
    ann_factor = _annualization_factor(equity_curve)
    sharpe = _sharpe(returns, ann_factor)
    sortino = _sortino(returns, ann_factor)
    max_dd_pct = _max_drawdown_pct(equity_curve)
    total_return_pct = ((final - initial) / initial * 100.0) if initial > 0 else 0.0
    cagr_pct = _cagr(initial, final, equity_curve)

    return Metrics(
        total_return_pct=total_return_pct,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown_pct=max_dd_pct,
        profit_factor=profit_factor,
        expectancy=expectancy,
        win_rate_pct=win_rate_pct,
        avg_win=avg_win,
        avg_loss=avg_loss,
        avg_r=avg_r,
        num_trades=num_trades,
        num_winners=num_winners,
        num_losers=num_losers,
        initial_equity=initial,
        final_equity=final,
        cagr_pct=cagr_pct,
    )


def format_report(metrics: Metrics, *, title: str = "Backtest report") -> str:
    """Render a Metrics object as a markdown table."""
    m = metrics
    pf = "inf" if math.isinf(m.profit_factor) else f"{m.profit_factor:.2f}"
    sortino = "inf" if math.isinf(m.sortino) else f"{m.sortino:.2f}"
    return "\n".join([
        f"# {title}",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total return | {m.total_return_pct:+.2f}% |",
        f"| CAGR | {m.cagr_pct:+.2f}% |",
        f"| Sharpe | {m.sharpe:.2f} |",
        f"| Sortino | {sortino} |",
        f"| Max drawdown | {m.max_drawdown_pct:.2f}% |",
        f"| Profit factor | {pf} |",
        f"| Expectancy | {m.expectancy:+.4f} |",
        f"| Avg R | {m.avg_r:+.2f} |",
        f"| Win rate | {m.win_rate_pct:.1f}% ({m.num_winners}/{m.num_trades}) |",
        f"| Avg win | {m.avg_win:+.4f} |",
        f"| Avg loss | {m.avg_loss:+.4f} |",
        f"| Initial equity | ${m.initial_equity:.2f} |",
        f"| Final equity | ${m.final_equity:.2f} |",
        f"| Trades | {m.num_trades} (W: {m.num_winners}, L: {m.num_losers}) |",
    ])
