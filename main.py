"""
Crypto Trading Bot - Main Entry Point.

Integrates: Signal Generator + Paper Trader + Telegram Bot. Runs three
loops on separate threads (signal scan, position monitor, telegram poll)
guarded by a shared shutdown Event so Ctrl+C is responsive.
"""

from __future__ import annotations

import json
import logging
import os
import signal as _signal
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any

import logging_config
from config import (
    BLACKLIST_DURATION,
    COMMAND_INTERVAL,
    HTTP_TIMEOUT,  # noqa: F401  (used via TelegramBot)
    POSITION_CHECK_INTERVAL,
    SCAN_INTERVAL,
    SCREENING_COOLDOWN,
    SCREENING_ENABLED,
    SCREENING_INTERVAL,
    SCREENING_MIN_VOLUME,
    SIGNAL_RATE_LIMIT,
    STATE_FILE,
    SUMMARY_INTERVAL,
    SYMBOLS,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TOP_N_COINS,
    TRADING_ENABLED,
)
from paper_trader import PaperTrader
from screener import CryptoScreener
from signal_generator import SignalGenerator
from telegram_bot import TelegramBot, esc
from tp_sl_calculator import calculate_dynamic_tp_sl

logger = logging.getLogger(__name__)


# Path next to the trader state for things we want to persist across restarts
# but that aren't part of trading state itself (e.g. Telegram update offset).
def _bot_meta_path() -> str:
    base = os.path.dirname(STATE_FILE) or "."
    return os.path.join(base, "bot_meta.json")


def _load_bot_meta() -> dict[str, Any]:
    path = _bot_meta_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as fh:
            return json.load(fh) or {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load bot meta: %s", exc)
        return {}


def _save_bot_meta(meta: dict[str, Any]) -> None:
    path = _bot_meta_path()
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(meta, fh)
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("Failed to save bot meta: %s", exc)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


class TradingBot:
    """Owns the trader/exchange/telegram and orchestrates the loops."""

    def __init__(self) -> None:
        self.signal_gen = SignalGenerator()
        # Reuse the same ccxt instance to share rate limiter across modules.
        self.screener = (
            CryptoScreener(min_volume_usd=SCREENING_MIN_VOLUME, exchange=self.signal_gen.exchange)
            if SCREENING_ENABLED
            else None
        )
        self.trader = PaperTrader()
        self.telegram = TelegramBot()

        self._shutdown = threading.Event()
        self.last_signal_time: dict[str, float] = {}
        self.scan_interval = SCAN_INTERVAL
        self.position_check_interval = POSITION_CHECK_INTERVAL
        self.active_symbols: list[str] = list(SYMBOLS) if not SCREENING_ENABLED else []
        self.trading_enabled = TRADING_ENABLED

        self.last_screening_time = 0.0
        self.screening_cooldown = SCREENING_COOLDOWN
        self.blacklisted_coins: dict[str, float] = {}
        self.blacklist_duration = BLACKLIST_DURATION

        self.command_interval = COMMAND_INTERVAL

        meta = _load_bot_meta()
        self.last_update_id = int(meta.get("last_update_id", 0))

        # Pending destructive-command confirmations: cmd -> deadline ts
        self._pending_confirm: dict[str, float] = {}

        # Thread-safety lock for shared mutable state
        self._lock = threading.Lock()

        # Load trader state if present.
        self.trader.load_state()

    # ------------------------------ shutdown ----------------------------- #

    def _handle_signal(self, signum, frame) -> None:  # noqa: ARG002
        logger.info("Shutdown signal %s received", signum)
        self._shutdown.set()

    # ------------------------------ telegram ----------------------------- #

    def _persist_meta(self) -> None:
        _save_bot_meta({"last_update_id": self.last_update_id})

    def _telegram_handler_loop(self) -> None:
        # Pre-prime offset to skip backlog at first run after big crashes.
        while not self._shutdown.is_set():
            try:
                self._poll_commands()
            except Exception as exc:
                logger.exception("telegram handler error: %s", exc)
            self._shutdown.wait(self.command_interval)

    def _poll_commands(self) -> None:
        updates = self.telegram.get_updates(offset=self.last_update_id + 1)
        if not updates or "result" not in updates:
            return
        for update in updates["result"]:
            if "message" not in update or "text" not in update["message"]:
                self.last_update_id = max(self.last_update_id, int(update.get("update_id", 0)))
                continue

            chat_id = update["message"]["chat"]["id"]
            from_id = update["message"].get("from", {}).get("id")
            text = update["message"]["text"].strip()
            update_id = int(update["update_id"])

            if update_id <= self.last_update_id:
                continue
            self.last_update_id = update_id
            self._persist_meta()

            # Authorize: chat *and* sender (if available) must match the
            # configured chat id.
            if str(chat_id) != str(TELEGRAM_CHAT_ID):
                continue
            if from_id is not None and str(from_id) != str(TELEGRAM_CHAT_ID):
                continue

            try:
                self._handle_command(text)
            except Exception as exc:
                logger.exception("command %r failed: %s", text, exc)
                self.telegram.send_error(f"Command failed: {exc}")

    def _handle_command(self, text: str) -> None:
        cmd = text.lower().split(maxsplit=1)[0] if text else ""

        if cmd in {"/positions", "/pos"}:
            with self._lock:
                positions_copy = dict(self.trader.positions)
            # Fetch live prices and compute unrealized PnL
            live_pnls: dict[str, dict[str, float]] = {}
            for sym in positions_copy:
                try:
                    ticker = self.signal_gen.exchange.fetch_ticker(sym)
                    price = float(ticker["last"])
                    pos = positions_copy[sym]
                    pos_data = pos.to_dict() if hasattr(pos, "to_dict") else pos
                    entry = float(pos_data["entry_price"])
                    qty = float(pos_data["quantity"])
                    side = "LONG" if pos_data["type"] == "BUY" else "SHORT"
                    if side == "LONG":
                        pnl = (price - entry) * qty
                    else:
                        pnl = (entry - price) * qty
                    pnl_pct = (pnl / float(pos_data.get("margin", qty * entry))) * 100
                    live_pnls[sym] = {"price": price, "pnl": pnl, "pnl_pct": pnl_pct}
                except Exception as exc:
                    logger.warning("Failed to fetch price for live PnL %s: %s", sym, exc)
            self.telegram.send_positions(positions_copy, live_pnls)
            return

        if cmd in {"/pnl", "/p&l"}:
            with self._lock:
                summary = self.trader.get_portfolio_summary()
            self.telegram.send_pnl(summary)
            return

        if cmd == "/status":
            with self._lock:
                summary = self.trader.get_portfolio_summary()
            self.telegram.send_portfolio_summary(summary)
            return

        if cmd in {"/start", "/help"}:
            self.telegram.send_message(self._help_text())
            return

        if cmd == "/pause":
            with self._lock:
                self.trading_enabled = False
            self.telegram.send_control_response(
                "PAUSE", True,
                "Trading paused. Existing positions still monitored.",
            )
            logger.info("Trading paused")
            return

        if cmd == "/resume":
            with self._lock:
                self.trading_enabled = True
            self.telegram.send_control_response(
                "RESUME", True, "Trading resumed.",
            )
            logger.info("Trading resumed")
            return

        if cmd == "/close":
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                self.telegram.send_control_response("CLOSE", False, "Usage: /close SYMBOL")
                return
            self._do_close(parts[1].strip())
            return

        if cmd == "/closeall":
            self._handle_destructive("/closeall", text, self._do_closeall,
                                     "This will close ALL open positions.")
            return

        if cmd == "/reset":
            self._handle_destructive("/reset", text, self._do_reset,
                                     "This will close ALL positions AND reset capital.")
            return

        if cmd == "/screen":
            if not (self.screener and SCREENING_ENABLED):
                self.telegram.send_message("❌ Screening not enabled")
                return
            self.telegram.send_message("🔍 Running manual screening...")
            top_picks = self.screener.get_top_picks(limit=10, min_score=1)
            self.send_screening_results(top_picks)
            self.last_screening_time = time.time()
            return

        # Unknown command: ignore silently.

    @staticmethod
    def _help_text() -> str:
        return (
            "🤖 <b>Crypto Trading Bot Commands</b>\n\n"
            "📊 <b>Portfolio:</b>\n"
            "• /positions — View open positions\n"
            "• /pnl — View P&amp;L summary\n"
            "• /status — Portfolio overview\n\n"
            "🎮 <b>Control:</b>\n"
            "• /pause — Pause trading (no new positions)\n"
            "• /resume — Resume trading\n"
            "• /close SYMBOL — Close a specific position (e.g. /close SOL)\n"
            "• /closeall confirm — Close all open positions\n"
            "• /reset confirm — Reset capital (closes all positions)\n"
            "• /screen — Manual screening trigger\n\n"
            "⚙️ <b>Bot Info:</b>\n"
            "• /start — Start bot\n"
            "• /help — Show this help\n"
        )

    def _handle_destructive(self, cmd: str, text: str, action, warning: str) -> None:
        # Treat explicit /closeall confirm or /reset confirm as one-shot, else
        # ask for confirmation valid for 60 seconds.
        parts = text.split()
        if len(parts) >= 2 and parts[1].lower() in {"confirm", "yes", "y"}:
            action()
            return
        deadline = time.time() + 60
        self._pending_confirm[cmd] = deadline
        self.telegram.send_message(
            f"⚠️ <b>CONFIRM REQUIRED</b>\n\n{esc(warning)}\n\nReply with <code>{esc(cmd)} confirm</code> within 60s to proceed."
        )

    def _do_close(self, sym_text: str) -> None:
        sym = sym_text.upper()
        if "/" not in sym:
            sym = f"{sym}/USDT"
        with self._lock:
            has_position = sym in self.trader.positions
        if not has_position:
            self.telegram.send_control_response("CLOSE", False, f"No open position for {sym}")
            return
        try:
            ticker = self.signal_gen.exchange.fetch_ticker(sym)
            with self._lock:
                result = self.trader.close_position(sym, float(ticker["last"]), "MANUAL")
            self.telegram.send_position_closed(result)
            logger.info("Manually closed %s", sym)
        except Exception as exc:
            self.telegram.send_control_response("CLOSE", False, f"Error closing position: {exc}")

    def _do_closeall(self) -> None:
        with self._lock:
            symbols = list(self.trader.positions.keys())
        if not symbols:
            self.telegram.send_control_response("CLOSEALL", False, "No open positions")
            return
        closed = 0
        failed: list[str] = []
        for sym in symbols:
            try:
                ticker = self.signal_gen.exchange.fetch_ticker(sym)
                with self._lock:
                    self.trader.close_position(sym, float(ticker["last"]), "MANUAL")
                closed += 1
            except Exception as exc:
                logger.warning("Failed to close %s: %s", sym, exc)
                failed.append(sym)
        msg = f"Closed {closed} position(s)"
        if failed:
            msg += f"; failed: {', '.join(failed)}"
        self.telegram.send_control_response("CLOSEALL", not failed, msg)
        logger.info("Closeall summary: closed=%d failed=%s", closed, failed)

    def _do_reset(self) -> None:
        self._do_closeall()
        with self._lock:
            self.trader.reset()
            self.trader.save_state()
        self.telegram.send_control_response(
            "RESET", True, f"Capital reset to ${self.trader.initial_capital:.2f}",
        )
        logger.info("Capital reset to $%.2f", self.trader.initial_capital)

    # ------------------------------ trading ------------------------------ #

    def process_signal(self, signal_data: dict[str, Any]) -> None:
        symbol = signal_data["symbol"]
        signal_type = signal_data["signal"]

        # Skip stablecoins entirely
        base = symbol.split("/")[0] if "/" in symbol else symbol
        if base in {"USDT", "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "EUR",
                    "USDD", "USDP", "SUSD", "GUSD", "USDe", "USD1", "PYUSD",
                    "AEUR", "EURI", "CUSD", "CEUR"}:
            logger.debug("Skipping stablecoin signal: %s", symbol)
            return

        # Notify on actionable signals only to avoid spam on HOLDs.
        if signal_type in {"BUY", "STRONG_BUY", "SELL"}:
            self.telegram.send_signal(signal_data)

        with self._lock:
            trading_on = self.trading_enabled
            has_position = symbol in self.trader.positions

        if not trading_on:
            logger.debug("Trading disabled, not opening %s", symbol)
            return

        if signal_type not in {"BUY", "STRONG_BUY", "SELL"}:
            return

        if has_position:
            logger.debug("Already have position for %s, skipping", symbol)
            return

        # Recompute fresh TP/SL using closed candles right before entry.
        df = self.signal_gen.fetch_ohlcv(symbol)
        if df is not None and len(df) >= 50:
            df = self.signal_gen.calculate_indicators(df)
            current_price = float(df["close"].iloc[-1])
            levels = calculate_dynamic_tp_sl(df, current_price, signal_type)
            tp = levels["tp"]
            sl = levels["sl"]
            rr = levels["rr_ratio"]
        else:
            current_price = float(signal_data.get("price", 0) or 0)
            tp = signal_data.get("tp")
            sl = signal_data.get("sl")
            rr = signal_data.get("rr_ratio")

        with self._lock:
            position = self.trader.open_position(
                symbol, current_price, signal_type, tp=tp, sl=sl, rr_ratio=rr,
            )

        if "error" in position:
            err = position["error"]
            msg = position.get("message", "")
            if err == "INSUFFICIENT_CAPITAL":
                self.telegram.send_message(
                    "⚠️ <b>INSUFFICIENT CAPITAL</b>\n\n"
                    f"Signal: {esc(signal_type)} {esc(symbol)}\n"
                    f"Price: ${current_price:.4f}\n\n{esc(msg)}"
                )
                logger.warning("Cannot open %s: %s", symbol, msg)
            elif err == "RISK_RULE_VIOLATION":
                self.telegram.send_risk_alert("warning", msg)
                logger.warning("Risk rule violation for %s: %s", symbol, msg)
            else:
                logger.error("Error opening position: %s", position)
            return

        self.telegram.send_position_opened(position)
        logger.info("Opened position %s @ $%.4f", symbol, current_price)

    def check_open_positions(self) -> None:
        with self._lock:
            symbols = list(self.trader.positions.keys())
        if not symbols:
            return

        bars: dict[str, dict[str, float]] = {}
        for symbol in symbols:
            try:
                ohlcv = self.signal_gen.exchange.fetch_ohlcv(
                    symbol, timeframe="1m", limit=1
                )
                if ohlcv:
                    _, _o, h, low, c, _v = ohlcv[-1]
                    bars[symbol] = {"high": float(h), "low": float(low), "last": float(c)}
                else:
                    ticker = self.signal_gen.exchange.fetch_ticker(symbol)
                    last = float(ticker["last"])
                    bars[symbol] = {"high": last, "low": last, "last": last}

                with self._lock:
                    trailing = self.trader.update_trailing_stop(symbol, bars[symbol]["last"])
                if trailing:
                    self.telegram.send_trailing_stop_update(trailing)
                    logger.info(
                        "Trailing stop updated for %s: $%.4f -> $%.4f",
                        symbol, trailing["old_sl"], trailing["new_sl"],
                    )
            except Exception as exc:
                logger.warning("Failed to fetch price for %s: %s", symbol, exc)

        with self._lock:
            closed = self.trader.check_positions(bars)
        for position in closed:
            self.telegram.send_position_closed(position)
            logger.info(
                "Closed position %s reason=%s pnl=$%.4f",
                position["symbol"], position["close_reason"], position["pnl"],
            )

            if position.get("close_reason") in {"STOP_LOSS", "LIQUIDATION"}:
                self.blacklist_coin(position["symbol"], position["close_reason"])
            if self.screener and SCREENING_ENABLED:
                self.trigger_screening(reason=f"{position['symbol']} {position['close_reason']}")

    # ------------------------------ screening ---------------------------- #

    def can_trigger_screening(self) -> tuple[bool, str]:
        with self._lock:
            max_pos_reached = len(self.trader.positions) >= self.trader.max_positions
        if max_pos_reached:
            return False, "Max positions reached"
        if time.time() - self.last_screening_time < self.screening_cooldown:
            remaining = int(self.screening_cooldown - (time.time() - self.last_screening_time))
            return False, f"Cooldown: {remaining}s remaining"
        return True, "OK"

    def trigger_screening(self, reason: str = "Position closed") -> None:
        ok, info = self.can_trigger_screening()
        if not ok:
            logger.debug("Cannot trigger screening: %s", info)
            return
        if not self.screener:
            return
        logger.info("Triggering re-screening (%s)", reason)
        try:
            top_picks = self.screener.get_top_picks(limit=5, min_score=1)
            if not top_picks:
                logger.info("No re-screening signals")
                return
            with self._lock:
                existing = set(self.trader.positions.keys())
            self.cleanup_blacklist()
            filtered = [
                p for p in top_picks
                if p["symbol"] not in existing and p["symbol"] not in self.blacklisted_coins
            ]
            if not filtered:
                logger.info("All re-screening picks filtered (existing/blacklisted)")
                return
            best = filtered[0]
            logger.info("Best re-screening signal: %s score=%s", best["symbol"], best["score"])
            self.process_signal(best)
            with self._lock:
                self.last_screening_time = time.time()
            self.telegram.send_message(
                "🔍 <b>RE-SCREENING TRIGGERED</b>\n\n"
                f"Reason: {esc(reason)}\n"
                f"Best Signal: {esc(best['symbol'])}\n"
                f"Score: {esc(best['score'])}\n\n"
                "<i>Position opened automatically.</i>"
            )
        except Exception as exc:
            logger.exception("Re-screening error: %s", exc)
            self.telegram.send_message(f"⚠️ Re-screening error: {esc(exc)}")

    def cleanup_blacklist(self) -> None:
        now = time.time()
        expired = [s for s, ts in self.blacklisted_coins.items() if now - ts > self.blacklist_duration]
        for s in expired:
            del self.blacklisted_coins[s]
        if expired:
            logger.info("Cleaned %d expired blacklist entries", len(expired))

    def blacklist_coin(self, symbol: str, reason: str = "SL_HIT") -> None:
        self.blacklisted_coins[symbol] = time.time()
        logger.info("Blacklisted %s for %ds (%s)", symbol, self.blacklist_duration, reason)

    def send_screening_results(self, picks: list[dict[str, Any]]) -> None:
        if not picks:
            return
        lines = [
            "🔍 <b>MARKET SCREENER RESULTS</b>",
            "",
            f"Top {len(picks)} coins ranked by signal strength:",
            "",
        ]
        for i, pick in enumerate(picks[:5], 1):
            ico = "🟢" if pick["signal"] == "BUY" else ("🔴" if pick["signal"] == "SELL" else "🟡")
            lines.extend([
                f"{i}. {ico} <b>{esc(pick['symbol'])}</b>",
                f"   Price: ${float(pick['price']):.4f}",
                f"   RSI: {float(pick['rsi']):.1f} | Score: {esc(pick['score'])}",
                f"   24h: {float(pick.get('change_24h', 0)):+.2f}%",
            ])
            if pick.get("tp") and pick.get("sl"):
                lines.append(
                    f"   TP: ${float(pick['tp']):.4f} (+{float(pick.get('tp_pct', 0)):.1f}%)"
                )
                lines.append(
                    f"   SL: ${float(pick['sl']):.4f} (-{float(pick.get('sl_pct', 0)):.1f}%)"
                )
                if pick.get("rr_ratio"):
                    lines.append(f"   R:R: {esc(pick['rr_ratio'])}:1")
            lines.append("")
        lines.append(f"<i>Scan time: {esc(_utc_iso())}</i>")
        self.telegram.send_message("\n".join(lines))

    # ------------------------------ loops -------------------------------- #

    def _position_monitor_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                self.check_open_positions()
            except Exception as exc:
                logger.exception("position monitor error: %s", exc)
            self._shutdown.wait(self.position_check_interval)

    def _scan_loop(self) -> None:
        last_screening_time = 0.0
        last_summary_time = time.time()

        while not self._shutdown.is_set():
            try:
                if self.screener and SCREENING_ENABLED and time.time() - last_screening_time > SCREENING_INTERVAL:
                    logger.info("Running market screener...")
                    top_picks = self.screener.get_top_picks(limit=TOP_N_COINS, min_score=1)
                    if top_picks:
                        with self._lock:
                            self.active_symbols = [p["symbol"] for p in top_picks]
                        logger.info("Selected %d coins: %s", len(self.active_symbols),
                                    ", ".join(self.active_symbols))
                        for symbol in self.active_symbols:
                            with self._lock:
                                self.last_signal_time[symbol] = 0
                        self.send_screening_results(top_picks)
                    last_screening_time = time.time()
                    with self._lock:
                        self.last_screening_time = last_screening_time

                with self._lock:
                    active = list(self.active_symbols)
                logger.info("[%s] Scanning %d coins", _utc_iso(), len(active))
                for symbol in active:
                    if self._shutdown.is_set():
                        break
                    signal_data = self.signal_gen.generate_signal(symbol)
                    logger.info(
                        "  %s: %s @ $%.4f", signal_data.get("symbol"),
                        signal_data.get("signal"), signal_data.get("price", 0) or 0,
                    )

                    with self._lock:
                        has_position = symbol in self.trader.positions

                    if has_position:
                        continue

                    with self._lock:
                        last_sig = self.last_signal_time.get(symbol, 0)
                    if time.time() - last_sig < SIGNAL_RATE_LIMIT:
                        continue
                    with self._lock:
                        self.last_signal_time[symbol] = time.time()
                    self.process_signal(signal_data)

                if time.time() - last_summary_time > SUMMARY_INTERVAL:
                    with self._lock:
                        summary = self.trader.get_portfolio_summary()
                    self.telegram.send_portfolio_summary(summary)
                    last_summary_time = time.time()

                with self._lock:
                    self.trader.save_state()
            except Exception as exc:
                logger.exception("scan loop error: %s", exc)
                self.telegram.send_error(f"Error in scan loop: {exc}")

            self._shutdown.wait(self.scan_interval)

    def run(self) -> None:
        _signal.signal(_signal.SIGINT, self._handle_signal)
        _signal.signal(_signal.SIGTERM, self._handle_signal)

        self.telegram.send_message(
            "🚀 <b>Trading Bot Started</b>\n\n"
            f"<b>Mode:</b> Paper Trading\n"
            f"<b>Symbols:</b> {esc(', '.join(SYMBOLS))}\n"
            f"<b>Scan Interval:</b> {self.scan_interval // 60} min\n"
            f"<b>Position Check:</b> every {self.position_check_interval}s\n\n"
            "<i>Monitoring markets...</i>"
        )
        logger.info("Trading Bot Started")

        threads = [
            threading.Thread(target=self._telegram_handler_loop, name="telegram", daemon=True),
            threading.Thread(target=self._position_monitor_loop, name="positions", daemon=True),
        ]
        for t in threads:
            t.start()

        try:
            self._scan_loop()
        finally:
            self._shutdown.set()
            for t in threads:
                t.join(timeout=5.0)
            self.trader.save_state()
            self._persist_meta()
            self.telegram.send_message("🛑 Trading Bot Stopped")
            logger.info("Bot stopped. State saved.")


def main() -> None:
    logging_config.setup_logging()
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("Please configure TELEGRAM_BOT_TOKEN in .env")
        sys.exit(1)
    if TELEGRAM_CHAT_ID == "YOUR_CHAT_ID_HERE":
        logger.error("Please configure TELEGRAM_CHAT_ID in .env")
        sys.exit(1)

    TradingBot().run()


if __name__ == "__main__":
    main()
