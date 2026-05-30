"""
Real trading safety executor for USDT-M futures.

Default bot remains paper. This module only runs when REAL_TRADING_ENABLED=true
and manual confirmation file exists (unless disabled explicitly).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from config import (
    LEVERAGE,
    REAL_CONFIRM_FILE,
    REAL_MAX_DAILY_LOSS_PCT,
    REAL_MAX_LEVERAGE,
    REAL_MAX_POSITIONS,
    REAL_MAX_SAME_DIRECTION,
    REAL_MIN_BALANCE_USDT,
    REAL_MIN_NOTIONAL_USDT,
    REAL_ORDER_TYPE,
    REAL_POSITION_SIZE_PCT,
    REAL_REQUIRE_MANUAL_CONFIRM,
)

logger = logging.getLogger(__name__)


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@dataclass
class RealPosition:
    symbol: str
    type: str  # BUY=LONG, SELL=SHORT
    entry_price: float
    quantity: float
    size_usd: float
    margin: float
    leverage: int
    take_profit: float
    stop_loss: float
    opened_at: str
    status: str = "OPEN"
    order_id: str | None = None
    raw_order: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "type": self.type,
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "size_usd": self.size_usd,
            "margin": self.margin,
            "leverage": self.leverage,
            "take_profit": self.take_profit,
            "stop_loss": self.stop_loss,
            "opened_at": self.opened_at,
            "status": self.status,
            "order_id": self.order_id,
            "raw_order": self.raw_order,
        }


class RealTrader:
    """Small real futures executor with hard safety caps."""

    def __init__(self, exchange) -> None:
        self.exchange = exchange
        self.positions: dict[str, RealPosition] = {}
        self.max_positions = REAL_MAX_POSITIONS
        self.max_same_direction = REAL_MAX_SAME_DIRECTION
        self.leverage = min(LEVERAGE, REAL_MAX_LEVERAGE)
        self.position_size_pct = REAL_POSITION_SIZE_PCT / 100.0
        self.max_daily_loss_pct = REAL_MAX_DAILY_LOSS_PCT
        self.daily_pnl = 0.0
        self.day_start_equity: float | None = None

    def safety_ready(self) -> tuple[bool, str]:
        if REAL_REQUIRE_MANUAL_CONFIRM and not os.path.exists(REAL_CONFIRM_FILE):
            return False, f"Real trading blocked: missing confirm file {REAL_CONFIRM_FILE}"
        if self.leverage > REAL_MAX_LEVERAGE:
            return False, f"Real leverage too high ({self.leverage}>{REAL_MAX_LEVERAGE})"
        if self.max_positions > REAL_MAX_POSITIONS:
            return False, "Real max positions exceeds cap"
        return True, "OK"

    def _free_usdt(self) -> float:
        bal = self.exchange.fetch_balance()
        usdt = bal.get("USDT") or {}
        free = usdt.get("free")
        if free is None:
            free = bal.get("free", {}).get("USDT", 0)
        return float(free or 0)

    def _total_usdt(self) -> float:
        bal = self.exchange.fetch_balance()
        usdt = bal.get("USDT") or {}
        total = usdt.get("total")
        if total is None:
            total = bal.get("total", {}).get("USDT", 0)
        return float(total or 0)

    def get_portfolio_summary(self) -> dict[str, Any]:
        try:
            total = self._total_usdt()
            free = self._free_usdt()
        except Exception:
            total = 0.0
            free = 0.0
        return {
            "initial_capital": self.day_start_equity or total,
            "current_capital": total,
            "locked_capital": max(total - free, 0.0),
            "available_capital": free,
            "total_pnl": total - (self.day_start_equity or total),
            "total_pnl_pct": ((total - (self.day_start_equity or total)) / (self.day_start_equity or total) * 100) if (self.day_start_equity or total) else 0.0,
            "open_positions": len(self.positions),
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "daily_pnl": self.daily_pnl,
        }

    def can_open_position(self) -> tuple[bool, str]:
        ok, msg = self.safety_ready()
        if not ok:
            return ok, msg
        if len(self.positions) >= self.max_positions:
            return False, f"Real max positions reached ({self.max_positions})"
        free = self._free_usdt()
        if free < REAL_MIN_BALANCE_USDT:
            return False, f"Real free balance too low (${free:.2f} < ${REAL_MIN_BALANCE_USDT:.2f})"
        if self.day_start_equity is None:
            self.day_start_equity = max(self._total_usdt(), 0.0)
        if self.day_start_equity > 0:
            daily_loss_pct = (self.daily_pnl / self.day_start_equity) * 100
            if daily_loss_pct <= -self.max_daily_loss_pct:
                return False, f"Real daily loss limit hit ({daily_loss_pct:.1f}% < -{self.max_daily_loss_pct}%)"
        return True, "OK"

    def can_open_direction(self, position_type: str) -> tuple[bool, str]:
        same = sum(1 for p in self.positions.values() if p.type == position_type)
        if same >= self.max_same_direction:
            side = "LONG" if position_type == "BUY" else "SHORT"
            return False, f"Real max same-direction reached ({side}: {same}/{self.max_same_direction})"
        return True, "OK"

    def open_position(self, symbol: str, entry_price: float, signal_type: str = "BUY", tp: float | None = None, sl: float | None = None, rr_ratio: float | None = None) -> dict[str, Any]:
        position_type = "SELL" if signal_type == "SELL" else "BUY"
        side = "sell" if position_type == "SELL" else "buy"
        ok, reason = self.can_open_position()
        if not ok:
            return {"error": "REAL_RISK_RULE", "message": reason, "symbol": symbol, "signal": signal_type}
        ok_dir, reason_dir = self.can_open_direction(position_type)
        if not ok_dir:
            return {"error": "REAL_RISK_RULE", "message": reason_dir, "symbol": symbol, "signal": signal_type}
        if symbol in self.positions:
            return {"error": "DUPLICATE_POSITION", "message": f"Real position already tracked for {symbol}", "symbol": symbol}

        try:
            if hasattr(self.exchange, "set_leverage"):
                self.exchange.set_leverage(self.leverage, symbol)
        except Exception as exc:
            logger.warning("set_leverage failed for %s: %s", symbol, exc)

        free = self._free_usdt()
        margin = free * self.position_size_pct
        notional = margin * self.leverage
        if notional < REAL_MIN_NOTIONAL_USDT:
            return {"error": "REAL_MIN_NOTIONAL", "message": f"Notional ${notional:.2f} < ${REAL_MIN_NOTIONAL_USDT:.2f}", "symbol": symbol}

        ticker = self.exchange.fetch_ticker(symbol)
        price = float(ticker.get("last") or entry_price)
        amount = notional / price
        order = self.exchange.create_order(symbol, REAL_ORDER_TYPE, side, amount)
        avg = float(order.get("average") or order.get("price") or price)
        filled = float(order.get("filled") or amount)
        size_usd = avg * filled
        pos = RealPosition(
            symbol=symbol,
            type=position_type,
            entry_price=avg,
            quantity=filled,
            size_usd=size_usd,
            margin=size_usd / max(self.leverage, 1),
            leverage=self.leverage,
            take_profit=float(tp or 0),
            stop_loss=float(sl or 0),
            opened_at=_utc_now_str(),
            order_id=str(order.get("id")) if order.get("id") else None,
            raw_order=order,
        )
        self.positions[symbol] = pos
        logger.warning("REAL OPEN %s %s qty=%s avg=%s", symbol, side, filled, avg)
        return pos.to_dict()

    def close_position(self, symbol: str, exit_price: float, reason: str = "MANUAL") -> dict[str, Any]:
        pos = self.positions.get(symbol)
        if not pos:
            return {"error": "No real position tracked"}
        side = "buy" if pos.type == "SELL" else "sell"
        order = self.exchange.create_order(symbol, REAL_ORDER_TYPE, side, pos.quantity, params={"reduceOnly": True})
        avg = float(order.get("average") or order.get("price") or exit_price)
        if pos.type == "SELL":
            pnl = (pos.entry_price - avg) * pos.quantity
        else:
            pnl = (avg - pos.entry_price) * pos.quantity
        self.daily_pnl += pnl
        closed = pos.to_dict()
        closed.update({
            "exit_price": avg,
            "exit_time": _utc_now_str(),
            "pnl": pnl,
            "pnl_gross": pnl,
            "pnl_pct": (pnl / max(pos.margin, 1e-9)) * 100,
            "close_reason": reason,
            "raw_close_order": order,
        })
        del self.positions[symbol]
        logger.warning("REAL CLOSE %s %s pnl=%s", symbol, reason, pnl)
        return closed

    def update_trailing_stop(self, symbol: str, current_price: float):
        return None

    def check_positions(self, ohlcv_by_symbol: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
        closed: list[dict[str, Any]] = []
        for symbol, pos in list(self.positions.items()):
            bar = ohlcv_by_symbol.get(symbol) or {}
            high = float(bar.get("high", bar.get("last", 0.0)) or 0.0)
            low = float(bar.get("low", bar.get("last", 0.0)) or 0.0)
            if pos.type == "BUY":
                if pos.stop_loss and low <= pos.stop_loss:
                    closed.append(self.close_position(symbol, pos.stop_loss, "STOP_LOSS"))
                elif pos.take_profit and high >= pos.take_profit:
                    closed.append(self.close_position(symbol, pos.take_profit, "TAKE_PROFIT"))
            else:
                if pos.stop_loss and high >= pos.stop_loss:
                    closed.append(self.close_position(symbol, pos.stop_loss, "STOP_LOSS"))
                elif pos.take_profit and low <= pos.take_profit:
                    closed.append(self.close_position(symbol, pos.take_profit, "TAKE_PROFIT"))
        return closed

    def save_state(self, filename: str | None = None) -> None:  # API compatibility
        return None

    def load_state(self, filename: str | None = None) -> bool:  # API compatibility
        return False
