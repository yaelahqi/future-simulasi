"""Bar-by-bar backtest engine with no lookahead.

The engine reuses the same logic as the live paper trader:

- Indicators are produced by ``signal_generator.SignalGenerator.calculate_indicators``.
- Signals are produced by ``signal_generator.SignalGenerator.evaluate_dataframe``.
- TP/SL levels are produced by ``tp_sl_calculator.calculate_dynamic_tp_sl``.
- Liquidation, slippage and fee formulas are imported from ``paper_trader``.

For each bar ``t`` the engine:

1. **Checks open positions** against bar ``t``'s high/low for liquidation,
   stop-loss, take-profit (in that priority).
2. Applies funding cost (if configured) to any open positions on a fresh
   funding period (every 8h by default).
3. **Updates trailing stops** using bar ``t``'s close.
4. **Generates a signal** using the window ``df.iloc[: t+1]`` — i.e. only
   bars that have already closed at the moment of decision.
5. If the signal is actionable and bar ``t+1`` exists, **opens a position
   at bar ``t+1``'s open price** (the next bar). This avoids lookahead:
   the decision is made *after* bar ``t`` closes and the entry happens at
   the next available price.

After the last bar, all open positions are closed at the final close.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from paper_trader import (
    _apply_slippage,
    _fee,
    _liquidation_price,
)
from signal_generator import SignalGenerator
from tp_sl_calculator import calculate_dynamic_tp_sl

logger = logging.getLogger(__name__)


@dataclass
class BacktestSettings:
    """Parameters that control how the engine simulates the live trader."""

    initial_capital: float = 1_000.0
    leverage: int = 10
    position_size_pct: float = 0.33  # of total equity, mirrors PaperTrader
    max_positions: int = 3
    taker_fee_pct: float = 0.04  # %
    slippage_bps: float = 2.0
    funding_bps_per_8h: float = 0.0  # one-sided drag per funding cycle
    allow_long: bool = True
    allow_short: bool = True
    htf_filter_ma: int | None = None  # if set, require close > MA(htf_filter_ma) for LONG
    warmup_bars: int = 50  # don't trade until enough history for indicators
    # Overrides for default fallback levels when calculate_dynamic_tp_sl fails.
    fallback_tp_pct: float = 5.0
    fallback_sl_pct: float = 5.0


@dataclass
class _OpenPosition:
    type: str  # "BUY" or "SELL"
    entry_price: float
    quantity: float
    size_usd: float
    margin: float
    take_profit: float
    stop_loss: float
    liquidation_price: float
    rr_ratio: float | None
    risk: float
    opened_at: pd.Timestamp
    fees_paid: float = 0.0
    trailing_active: bool = False
    last_funding_ts: pd.Timestamp | None = None


@dataclass
class BacktestResult:
    settings: BacktestSettings
    equity_curve: pd.Series
    trades: list[dict[str, Any]]
    final_equity: float
    initial_equity: float
    bars_processed: int = field(default=0)


# Funding cycles run every 8h on Binance USDT-M; we use the same convention.
_FUNDING_INTERVAL = pd.Timedelta(hours=8)


def _maybe_charge_funding(
    pos: _OpenPosition,
    bar_ts: pd.Timestamp,
    funding_bps_per_8h: float,
) -> float:
    """Return funding cost (USD) accrued since the last funding charge.

    A flat per-8h drag is used as a conservative approximation. Positive
    cost is paid by the side facing the prevailing funding bias; we model
    it as drag for whichever side is open. Set to 0 to ignore funding.
    """
    if funding_bps_per_8h == 0:
        return 0.0
    if pos.last_funding_ts is None:
        pos.last_funding_ts = bar_ts
        return 0.0
    cycles = (bar_ts - pos.last_funding_ts) // _FUNDING_INTERVAL
    if cycles <= 0:
        return 0.0
    pos.last_funding_ts = pos.last_funding_ts + (_FUNDING_INTERVAL * cycles)
    return pos.size_usd * (funding_bps_per_8h / 10_000.0) * float(cycles)


def _passes_htf_filter(window: pd.DataFrame, signal_type: str, ma_len: int | None) -> bool:
    if ma_len is None or ma_len <= 0:
        return True
    if len(window) < ma_len:
        return False
    ma = window["close"].tail(ma_len).mean()
    last_close = window["close"].iloc[-1]
    if signal_type in {"BUY", "STRONG_BUY"}:
        return last_close > ma
    if signal_type == "SELL":
        return last_close < ma
    return True


def _open_position(
    settings: BacktestSettings,
    free_equity: float,
    total_equity: float,
    locked_capital: float,
    signal_type: str,
    entry_price: float,
    tp: float,
    sl: float,
    rr_ratio: float | None,
    bar_ts: pd.Timestamp,
) -> tuple[_OpenPosition, float] | None:
    """Open a single position. Returns (position, entry_fee) or None."""
    is_short = signal_type == "SELL"
    position_type = "SELL" if is_short else "BUY"

    target_margin = total_equity * settings.position_size_pct
    margin = max(0.0, min(target_margin, free_equity))
    if margin <= 0:
        return None

    side = "sell" if is_short else "buy"
    fill_price = _apply_slippage(entry_price, side)
    if fill_price <= 0:
        return None

    position_size = margin * settings.leverage
    quantity = position_size / fill_price
    entry_fee = _fee(position_size) * (settings.taker_fee_pct / 0.04)  # scale to setting

    liq_price = _liquidation_price(fill_price, settings.leverage, position_type)
    if is_short:
        if sl >= liq_price > 0:
            sl = liq_price * 0.999
    else:
        if 0 < liq_price and sl <= liq_price:
            sl = liq_price * 1.001

    risk = abs(fill_price - sl)
    pos = _OpenPosition(
        type=position_type,
        entry_price=fill_price,
        quantity=quantity,
        size_usd=position_size,
        margin=margin,
        take_profit=tp,
        stop_loss=sl,
        liquidation_price=liq_price,
        rr_ratio=rr_ratio,
        risk=risk,
        opened_at=bar_ts,
        fees_paid=entry_fee,
        last_funding_ts=bar_ts,
    )
    return pos, entry_fee


def _close_position(
    pos: _OpenPosition,
    exit_price: float,
    reason: str,
    bar_ts: pd.Timestamp,
    settings: BacktestSettings,
) -> dict[str, Any]:
    side = "buy" if pos.type == "SELL" else "sell"
    fill_price = _apply_slippage(exit_price, side)
    if pos.type == "SELL":
        gross = (pos.entry_price - fill_price) * pos.quantity
    else:
        gross = (fill_price - pos.entry_price) * pos.quantity

    exit_fee = _fee(pos.size_usd) * (settings.taker_fee_pct / 0.04)
    pos.fees_paid += exit_fee
    net = gross - exit_fee

    return {
        "type": pos.type,
        "entry_price": pos.entry_price,
        "exit_price": fill_price,
        "quantity": pos.quantity,
        "size_usd": pos.size_usd,
        "margin": pos.margin,
        "take_profit": pos.take_profit,
        "stop_loss": pos.stop_loss,
        "liquidation_price": pos.liquidation_price,
        "rr_ratio": pos.rr_ratio,
        "risk": pos.risk,
        "pnl": net,
        "pnl_gross": gross,
        "fees_paid": pos.fees_paid,
        "reason": reason,
        "opened_at": pos.opened_at,
        "closed_at": bar_ts,
    }


def _check_intra_bar(
    pos: _OpenPosition,
    bar: pd.Series,
) -> tuple[float, str] | None:
    """If TP/SL/liq is hit by this bar, return (fill_price, reason)."""
    high = float(bar["high"])
    low = float(bar["low"])

    if pos.type == "BUY":
        if pos.liquidation_price > 0 and low <= pos.liquidation_price:
            return pos.liquidation_price, "LIQUIDATION"
        if low <= pos.stop_loss:
            return pos.stop_loss, "STOP_LOSS"
        if high >= pos.take_profit:
            return pos.take_profit, "TAKE_PROFIT"
    elif pos.type == "SELL":
        if pos.liquidation_price > 0 and high >= pos.liquidation_price:
            return pos.liquidation_price, "LIQUIDATION"
        if high >= pos.stop_loss:
            return pos.stop_loss, "STOP_LOSS"
        if low <= pos.take_profit:
            return pos.take_profit, "TAKE_PROFIT"
    return None


def _update_trailing(pos: _OpenPosition, current_price: float) -> None:
    """Mirror of PaperTrader.update_trailing_stop, ratchet-only."""
    entry = pos.entry_price
    if entry <= 0:
        return

    if pos.type == "BUY":
        if current_price <= entry:
            return
        profit_pct = (current_price - entry) / entry
        new_sl: float | None = None
        if profit_pct >= 0.05:
            new_sl = current_price * 0.98
        elif profit_pct >= 0.03:
            new_sl = entry * 1.001
        if new_sl is None or new_sl <= pos.stop_loss:
            return
        pos.stop_loss = new_sl
        pos.trailing_active = True
    elif pos.type == "SELL":
        if current_price >= entry:
            return
        profit_pct = (entry - current_price) / entry
        new_sl = None
        if profit_pct >= 0.05:
            new_sl = current_price * 1.02
        elif profit_pct >= 0.03:
            new_sl = entry * 0.999
        if new_sl is None or new_sl >= pos.stop_loss:
            return
        pos.stop_loss = new_sl
        pos.trailing_active = True


def run_backtest(
    df: pd.DataFrame,
    settings: BacktestSettings | None = None,
    *,
    signal_generator: SignalGenerator | None = None,
    symbol: str = "",
) -> BacktestResult:
    """Run the strategy through ``df`` and return :class:`BacktestResult`.

    ``df`` must be sorted ascending by timestamp and contain the columns
    ``timestamp, open, high, low, close, volume``.
    """
    settings = settings or BacktestSettings()
    if df is None or len(df) < settings.warmup_bars + 5:
        raise ValueError("Not enough bars for backtest (need warmup_bars + 5 minimum)")
    if "timestamp" not in df.columns:
        raise ValueError("df must include a 'timestamp' column")

    sg = signal_generator or SignalGenerator(exchange=_NullExchange())

    # Compute indicators once on the full series; for each bar we use the
    # slice up to that bar to avoid lookahead. Since indicators (SMA/RSI/...)
    # are causal — value at time t depends only on bars ≤ t — slicing
    # afterwards produces identical results to recomputing per bar.
    indicators_df = sg.calculate_indicators(df)
    if indicators_df is None:
        raise ValueError("calculate_indicators returned None — series too short?")

    timestamps = pd.DatetimeIndex(indicators_df["timestamp"])
    capital = float(settings.initial_capital)
    locked_capital = 0.0
    trades: list[dict[str, Any]] = []
    equity_records: list[tuple[pd.Timestamp, float]] = []

    # Single-symbol backtests can only have one open position concept-wise
    # (no concurrent BUY+SELL on the same symbol at once); we enforce 1 open
    # at a time. For multi-symbol use the engine should be invoked per
    # symbol and equity merged externally.
    open_pos: _OpenPosition | None = None

    for i in range(settings.warmup_bars, len(indicators_df)):
        bar = indicators_df.iloc[i]
        bar_ts = timestamps[i]

        # 1. Check if the open position is hit by this bar's range.
        if open_pos is not None:
            funding_cost = _maybe_charge_funding(
                open_pos, bar_ts, settings.funding_bps_per_8h
            )
            if funding_cost:
                capital -= funding_cost
            hit = _check_intra_bar(open_pos, bar)
            if hit is not None:
                exit_price, reason = hit
                trade = _close_position(open_pos, exit_price, reason, bar_ts, settings)
                capital += trade["pnl"]
                locked_capital = max(0.0, locked_capital - open_pos.margin)
                trades.append(trade)
                open_pos = None
            else:
                # 2. Trailing stop (ratchet-only) on bar close.
                _update_trailing(open_pos, float(bar["close"]))

        # Mark equity at this bar.
        equity_records.append((bar_ts, capital))

        # 3. Evaluate signal on closed window. If we already have an open
        # position, we don't take another (single-position single-symbol).
        if open_pos is not None:
            continue
        if i + 1 >= len(indicators_df):
            continue  # no next bar to fill on

        window = indicators_df.iloc[: i + 1]
        sig = sg.evaluate_dataframe(window, symbol=symbol)
        signal_type = sig.get("signal", "HOLD")
        if signal_type not in {"BUY", "STRONG_BUY", "SELL"}:
            continue
        if signal_type == "SELL" and not settings.allow_short:
            continue
        if signal_type in {"BUY", "STRONG_BUY"} and not settings.allow_long:
            continue
        if not _passes_htf_filter(window, signal_type, settings.htf_filter_ma):
            continue

        # 4. Fill at next bar's open.
        next_bar = indicators_df.iloc[i + 1]
        fill_open = float(next_bar["open"])
        levels = calculate_dynamic_tp_sl(window, fill_open, signal_type)
        tp = float(levels.get("tp", 0.0) or 0.0)
        sl = float(levels.get("sl", 0.0) or 0.0)
        if tp <= 0 or sl <= 0:
            continue

        free_equity = capital - locked_capital
        new_pos = _open_position(
            settings,
            free_equity=free_equity,
            total_equity=capital,
            locked_capital=locked_capital,
            signal_type=signal_type,
            entry_price=fill_open,
            tp=tp,
            sl=sl,
            rr_ratio=float(levels.get("rr_ratio") or 0.0),
            bar_ts=timestamps[i + 1],
        )
        if new_pos is None:
            continue
        pos, entry_fee = new_pos
        capital -= entry_fee
        locked_capital += pos.margin
        open_pos = pos

    # End of data: close any open position at last close. Overwrite (not
    # append) the last equity record so a single timestamp doesn't appear
    # twice in the curve.
    if open_pos is not None:
        last_bar_ts = timestamps[-1]
        last_close = float(indicators_df.iloc[-1]["close"])
        trade = _close_position(open_pos, last_close, "END_OF_DATA", last_bar_ts, settings)
        capital += trade["pnl"]
        locked_capital = max(0.0, locked_capital - open_pos.margin)
        trades.append(trade)
        open_pos = None
        if equity_records and equity_records[-1][0] == last_bar_ts:
            equity_records[-1] = (last_bar_ts, capital)
        else:
            equity_records.append((last_bar_ts, capital))

    if not equity_records:
        equity_records.append((timestamps[-1], capital))
    equity_index, equity_values = zip(*equity_records, strict=False)
    equity_curve = pd.Series(
        list(equity_values),
        index=pd.DatetimeIndex(list(equity_index), name="timestamp"),
        name="equity",
    )

    return BacktestResult(
        settings=settings,
        equity_curve=equity_curve,
        trades=trades,
        final_equity=float(capital),
        initial_equity=float(settings.initial_capital),
        bars_processed=len(indicators_df) - settings.warmup_bars,
    )


class _NullExchange:
    """Sentinel passed to SignalGenerator when the engine never fetches data."""

    id = "null"

    def fetch_ohlcv(self, *args: Any, **kwargs: Any) -> list:
        return []
