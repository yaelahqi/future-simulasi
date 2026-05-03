"""
Paper Trading Module.

Simulates futures trades without real money. Models taker fee, slippage,
liquidation, and concurrent access from multiple threads. Tracks PnL,
positions, and trade history.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from config import (
    INITIAL_CAPITAL,
    LEVERAGE,
    LOG_FILE,
    MAX_DAILY_LOSS_PCT,
    MAX_LEVERAGE,
    MAX_POSITIONS,
    POSITION_SIZE_PCT,
    SLIPPAGE_BPS,
    STATE_FILE,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    TAKER_FEE_PCT,
)

logger = logging.getLogger(__name__)


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _utc_today():
    return datetime.now(timezone.utc).date()


@dataclass
class Position:
    symbol: str
    type: str  # "BUY" only for now (LONG-only bot)
    entry_price: float
    quantity: float
    size_usd: float
    margin: float
    leverage: int
    take_profit: float
    stop_loss: float
    liquidation_price: float
    tp_dynamic: bool = False
    rr_ratio: float | None = None
    trailing_stop_active: bool = False
    opened_at: str = field(default_factory=_utc_now_str)
    fees_paid: float = 0.0
    status: str = "OPEN"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Position:
        # Backwards-compatible: old state files lack newer fields.
        leverage = int(data.get("leverage", LEVERAGE))
        size_usd = float(data["size_usd"])
        margin = float(data.get("margin", size_usd / max(leverage, 1)))
        liq = float(data.get("liquidation_price", 0.0))
        return cls(
            symbol=data["symbol"],
            type=data["type"],
            entry_price=float(data["entry_price"]),
            quantity=float(data["quantity"]),
            size_usd=size_usd,
            margin=margin,
            leverage=leverage,
            take_profit=float(data["take_profit"]),
            stop_loss=float(data["stop_loss"]),
            liquidation_price=liq,
            tp_dynamic=bool(data.get("tp_dynamic", False)),
            rr_ratio=data.get("rr_ratio"),
            trailing_stop_active=bool(data.get("trailing_stop_active", False)),
            opened_at=data.get("opened_at", _utc_now_str()),
            fees_paid=float(data.get("fees_paid", 0.0)),
            status=data.get("status", "OPEN"),
        )


def _liquidation_price_long(entry: float, leverage: int) -> float:
    """Approx isolated-margin liquidation for a LONG.

    Maintenance margin ~0.5% (Binance USDT-M tiered, ignored). With pure
    isolated margin this is roughly when loss == margin: entry * (1 - 1/lev).
    """
    if leverage <= 0:
        return 0.0
    # Slightly conservative buffer for maintenance margin (0.5%).
    return entry * (1 - (1 / leverage) + 0.005)


def _apply_slippage(price: float, side: str) -> float:
    """Apply slippage in basis points. side='buy' adds, 'sell' subtracts."""
    bps = SLIPPAGE_BPS / 10_000.0
    if side == "buy":
        return price * (1 + bps)
    if side == "sell":
        return price * (1 - bps)
    return price


def _fee(notional: float) -> float:
    return abs(notional) * (TAKER_FEE_PCT / 100.0)


class PaperTrader:
    """Thread-safe paper trading engine for LONG-only futures positions."""

    def __init__(self) -> None:
        self.initial_capital: float = INITIAL_CAPITAL
        self.capital: float = INITIAL_CAPITAL  # equity (free + locked)
        self.leverage: int = min(LEVERAGE, MAX_LEVERAGE)
        self.positions: dict[str, Position] = {}
        self.trade_history: list[dict[str, Any]] = []
        self.locked_capital: float = 0.0  # margin locked in open positions
        self.daily_pnl: float = 0.0
        self.day_start_equity: float = INITIAL_CAPITAL
        self.last_reset_date = _utc_today()
        self.max_positions: int = MAX_POSITIONS
        self.position_size_pct: float = POSITION_SIZE_PCT / 100.0
        self.max_daily_loss_pct: float = MAX_DAILY_LOSS_PCT
        self._lock = RLock()
        self._ensure_log_dir()

    # ------------------------------ helpers ------------------------------ #

    @staticmethod
    def _ensure_log_dir() -> None:
        log_dir = os.path.dirname(LOG_FILE) or "."
        os.makedirs(log_dir, exist_ok=True)

    def _reset_daily_stats_locked(self) -> None:
        today = _utc_today()
        if today > self.last_reset_date:
            self.daily_pnl = 0.0
            self.last_reset_date = today
            self.day_start_equity = self.capital  # baseline for daily-loss check
            logger.info("Daily stats reset (UTC). New day: %s, baseline equity=$%.2f",
                        today, self.day_start_equity)

    # ------------------------------ public ------------------------------- #

    def reset_daily_stats(self) -> None:
        with self._lock:
            self._reset_daily_stats_locked()

    def can_open_position(self) -> tuple[bool, str]:
        """Check whether opening a new position is allowed."""
        with self._lock:
            self._reset_daily_stats_locked()

            if len(self.positions) >= self.max_positions:
                return False, f"Max positions reached ({self.max_positions})"

            # Daily loss is measured against the start-of-day equity so the
            # threshold tracks compounded capital. Falls back to initial_capital
            # for fresh sessions where day_start_equity is still the seed value.
            baseline = self.day_start_equity if self.day_start_equity > 0 else self.initial_capital
            daily_loss_pct = (self.daily_pnl / baseline) * 100
            if daily_loss_pct <= -self.max_daily_loss_pct:
                return False, f"Daily loss limit hit ({daily_loss_pct:.1f}% < -{self.max_daily_loss_pct}%)"

            available = self.capital - self.locked_capital
            if available <= 0:
                return False, f"No available capital (Locked: ${self.locked_capital:.2f})"

            return True, "OK"

    def open_position(
        self,
        symbol: str,
        entry_price: float,
        signal_type: str = "BUY",
        tp: float | None = None,
        sl: float | None = None,
        rr_ratio: float | None = None,
    ) -> dict[str, Any]:
        """Open a paper position. Returns position dict or {'error': ...}."""
        if signal_type != "BUY":
            return {
                "error": "UNSUPPORTED_SIGNAL",
                "message": f"Bot is LONG-only; got '{signal_type}'",
                "symbol": symbol,
                "signal": signal_type,
            }

        with self._lock:
            ok, reason = self.can_open_position()
            if not ok:
                return {"error": "RISK_RULE_VIOLATION", "message": reason,
                        "symbol": symbol, "signal": signal_type}

            if symbol in self.positions:
                return {"error": "DUPLICATE_POSITION",
                        "message": f"Position already open for {symbol}",
                        "symbol": symbol, "signal": signal_type}

            # Sizing is based on TOTAL equity so the percentage is honored
            # consistently regardless of how many positions are already open.
            equity = self.capital
            target_margin = equity * self.position_size_pct

            # Cap by available cash so we never over-allocate.
            available = self.capital - self.locked_capital
            margin_required = max(0.0, min(target_margin, available))
            if margin_required <= 0:
                return {
                    "error": "INSUFFICIENT_CAPITAL",
                    "message": f"No capital available. Free: ${available:.2f}",
                    "symbol": symbol,
                    "signal": signal_type,
                }

            fill_price = _apply_slippage(entry_price, "buy")
            position_size = margin_required * self.leverage
            quantity = position_size / fill_price
            entry_fee = _fee(position_size)

            # Pay entry fee from free equity immediately so PnL accounting matches reality.
            self.capital -= entry_fee

            if tp is not None and sl is not None:
                take_profit = float(tp)
                stop_loss = float(sl)
                is_dynamic = True
            else:
                take_profit = fill_price * (1 + TAKE_PROFIT_PCT / 100)
                stop_loss = fill_price * (1 - STOP_LOSS_PCT / 100)
                is_dynamic = False

            liq_price = _liquidation_price_long(fill_price, self.leverage)
            # Ensure SL never sits below liquidation: we'd be stopped before SL.
            if stop_loss <= liq_price:
                stop_loss = liq_price * 1.001

            position = Position(
                symbol=symbol,
                type="BUY",
                entry_price=fill_price,
                quantity=quantity,
                size_usd=position_size,
                margin=margin_required,
                leverage=self.leverage,
                take_profit=take_profit,
                stop_loss=stop_loss,
                liquidation_price=liq_price,
                tp_dynamic=is_dynamic,
                rr_ratio=rr_ratio,
                fees_paid=entry_fee,
            )

            self.positions[symbol] = position
            self.locked_capital += margin_required

            self._log_trade("OPEN", position.to_dict())
            return position.to_dict()

    def update_trailing_stop(self, symbol: str, current_price: float) -> dict[str, Any] | None:
        """Trail the stop loss for a profitable LONG position."""
        with self._lock:
            position = self.positions.get(symbol)
            if position is None or position.type != "BUY":
                return None
            if current_price <= position.entry_price:
                return None

            profit_pct = (current_price - position.entry_price) / position.entry_price
            new_sl: float | None = None
            if profit_pct >= 0.05:
                new_sl = current_price * 0.98  # 2% trailing
            elif profit_pct >= 0.03:
                new_sl = position.entry_price * 1.001  # breakeven + tiny buffer

            if new_sl is None or new_sl <= position.stop_loss:
                return None

            old_sl = position.stop_loss
            position.stop_loss = new_sl
            position.trailing_stop_active = True
            return {"symbol": symbol, "old_sl": old_sl, "new_sl": new_sl, "type": "trailing"}

    def close_position(self, symbol: str, exit_price: float, reason: str = "MANUAL") -> dict[str, Any]:
        """Close a position at ``exit_price`` (already a market price)."""
        with self._lock:
            position = self.positions.get(symbol)
            if position is None:
                return {"error": "No open position"}

            # Reset daily stats before booking PnL so multi-day flat periods
            # don't carry stale daily totals across days.
            self._reset_daily_stats_locked()

            # Apply exit-side slippage (LONG exit = sell). Liquidation/SL fills
            # are simulated at the trigger price *with* slippage already applied
            # by check_positions; here we still pay the slippage cost.
            fill_price = _apply_slippage(exit_price, "sell")

            pnl = (fill_price - position.entry_price) * position.quantity
            exit_fee = _fee(position.size_usd)
            net_pnl = pnl - exit_fee

            margin_basis = position.margin or 1.0
            pnl_pct = (net_pnl / margin_basis) * 100  # return on margin

            self.capital += net_pnl  # realize P&L
            self.daily_pnl += net_pnl
            self.locked_capital = max(0.0, self.locked_capital - position.margin)
            position.fees_paid += exit_fee
            position.status = "CLOSED"

            closed = position.to_dict()
            closed.update({
                "exit_price": fill_price,
                "exit_time": _utc_now_str(),
                "pnl": net_pnl,
                "pnl_gross": pnl,
                "pnl_pct": pnl_pct,
                "close_reason": reason,
            })

            del self.positions[symbol]
            self.trade_history.append(closed)
            self._log_trade("CLOSE", closed)
            return closed

    def check_positions(self, ohlcv_by_symbol: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
        """Inspect each open position for TP/SL/liquidation hits.

        ``ohlcv_by_symbol`` maps symbol -> {'high', 'low', 'last'}. Using the
        current candle's high/low (instead of just last) lets us catch hits
        that occurred between polls, matching how a real exchange would fill.
        """
        closed: list[dict[str, Any]] = []
        with self._lock:
            for symbol in list(self.positions.keys()):
                bar = ohlcv_by_symbol.get(symbol)
                if not bar:
                    continue

                position = self.positions[symbol]
                high = float(bar.get("high", bar.get("last", 0.0)))
                low = float(bar.get("low", bar.get("last", 0.0)))

                if position.type == "BUY":
                    # Liquidation has highest priority.
                    if position.liquidation_price > 0 and low <= position.liquidation_price:
                        result = self.close_position(symbol, position.liquidation_price, "LIQUIDATION")
                        closed.append(result)
                        continue
                    if low <= position.stop_loss:
                        result = self.close_position(symbol, position.stop_loss, "STOP_LOSS")
                        closed.append(result)
                        continue
                    if high >= position.take_profit:
                        result = self.close_position(symbol, position.take_profit, "TAKE_PROFIT")
                        closed.append(result)
                        continue
        return closed

    def get_portfolio_summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "initial_capital": self.initial_capital,
                "current_capital": self.capital,
                "locked_capital": self.locked_capital,
                "available_capital": self.capital - self.locked_capital,
                "total_pnl": self.capital - self.initial_capital,
                "total_pnl_pct": ((self.capital - self.initial_capital) / self.initial_capital) * 100
                if self.initial_capital > 0
                else 0.0,
                "open_positions": len(self.positions),
                "total_trades": len(self.trade_history),
                "winning_trades": len([t for t in self.trade_history if t.get("pnl", 0) > 0]),
                "losing_trades": len([t for t in self.trade_history if t.get("pnl", 0) <= 0]),
                "daily_pnl": self.daily_pnl,
            }

    # ------------------------------ persistence -------------------------- #

    def _log_trade(self, action: str, position: dict[str, Any]) -> None:
        entry = {"action": action, "timestamp": _utc_now_str(), **position}
        try:
            with open(LOG_FILE, "a") as fh:
                fh.write(json.dumps(entry, default=str) + "\n")
        except OSError as exc:  # pragma: no cover
            logger.warning("Failed to write trade log: %s", exc)

    def save_state(self, filename: str | None = None) -> None:
        path = filename or STATE_FILE
        with self._lock:
            payload = {
                "capital": self.capital,
                "initial_capital": self.initial_capital,
                "positions": {k: v.to_dict() for k, v in self.positions.items()},
                "trade_history": self.trade_history,
                "locked_capital": self.locked_capital,
                "daily_pnl": self.daily_pnl,
                "day_start_equity": self.day_start_equity,
                "last_reset_date": self.last_reset_date.isoformat(),
                "leverage": self.leverage,
            }
        # Write outside the lock to minimize lock duration; copy already taken.
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            tmp_dir = os.path.dirname(path) or "."
            fd, tmp_path = tempfile.mkstemp(prefix=".state-", suffix=".json", dir=tmp_dir)
            try:
                with os.fdopen(fd, "w") as fh:
                    json.dump(payload, fh, indent=2, default=str)
                os.replace(tmp_path, path)
            except Exception:
                # Cleanup tmpfile on failure.
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as exc:
            logger.error("Failed to save state to %s: %s", path, exc)

    def load_state(self, filename: str | None = None) -> bool:
        path = filename or STATE_FILE
        if not os.path.exists(path):
            return False
        try:
            with open(path) as fh:
                state = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to load state from %s: %s", path, exc)
            return False

        with self._lock:
            self.capital = float(state.get("capital", INITIAL_CAPITAL))
            self.initial_capital = float(state.get("initial_capital", self.initial_capital))
            raw_positions = state.get("positions", {}) or {}
            self.positions = {
                sym: Position.from_dict(pos) if isinstance(pos, dict) else pos
                for sym, pos in raw_positions.items()
            }
            self.trade_history = state.get("trade_history", []) or []
            self.locked_capital = float(state.get("locked_capital", 0.0))
            self.daily_pnl = float(state.get("daily_pnl", 0.0))
            self.day_start_equity = float(state.get("day_start_equity", self.capital))
            last_reset_str = state.get("last_reset_date")
            if last_reset_str:
                try:
                    self.last_reset_date = datetime.fromisoformat(last_reset_str).date()
                except (TypeError, ValueError):
                    self.last_reset_date = _utc_today()
            # Recompute locked_capital if stale.
            recomputed = sum(p.margin for p in self.positions.values())
            if abs(recomputed - self.locked_capital) > 1e-6:
                logger.info("Recomputed locked_capital: %.4f -> %.4f", self.locked_capital, recomputed)
                self.locked_capital = recomputed
        return True

    # ------------------------------ debug -------------------------------- #

    def reset(self) -> None:
        """Reset all state to initial values (does NOT close positions)."""
        with self._lock:
            self.capital = self.initial_capital
            self.locked_capital = 0.0
            self.daily_pnl = 0.0
            self.day_start_equity = self.initial_capital
            self.last_reset_date = _utc_today()
            self.positions.clear()
            self.trade_history.clear()
