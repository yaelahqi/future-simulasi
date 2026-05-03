"""
Telegram Bot Module.

Sends trading signals/alerts to a single Telegram chat and receives commands
from the user. Uses HTML parse mode with escaping to avoid the well-known
Markdown injection issues, and applies a hard request timeout to every
network call.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from typing import Any

import requests

from config import HTTP_TIMEOUT, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def esc(value: Any) -> str:
    """HTML-escape a value for safe inclusion in Telegram messages."""
    return html.escape(str(value), quote=False)


class TelegramBot:
    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        self.token = token or TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self._session = requests.Session()

    # ------------------------------ network ------------------------------ #

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any] | None:
        url = f"{self.base_url}/{path}"
        kwargs.setdefault("timeout", HTTP_TIMEOUT)
        try:
            resp = self._session.request(method, url, **kwargs)
            data = resp.json()
            if not data.get("ok", False):
                logger.warning("Telegram %s %s returned not-ok: %s", method, path, data.get("description"))
            return data
        except (requests.Timeout, requests.ConnectionError) as exc:
            logger.warning("Telegram %s %s network error: %s", method, path, exc)
        except Exception as exc:
            logger.exception("Telegram %s %s unexpected error: %s", method, path, exc)
        return None

    def send_message(self, text: str, parse_mode: str = "HTML") -> dict[str, Any] | None:
        return self._request(
            "POST",
            "sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
        )

    def get_updates(self, offset: int | None = None, long_poll_seconds: int = 20) -> dict[str, Any] | None:
        params: dict[str, Any] = {"timeout": long_poll_seconds}
        if offset is not None:
            params["offset"] = offset
        # Total client timeout = long-poll + slack so requests doesn't cut us
        # off before Telegram returns the long-poll batch.
        return self._request("GET", "getUpdates", params=params, timeout=long_poll_seconds + 5)

    def get_me(self) -> dict[str, Any] | None:
        return self._request("GET", "getMe")

    # ------------------------------ messages ----------------------------- #

    def send_signal(self, signal_data: dict[str, Any]) -> dict[str, Any] | None:
        emoji = {"BUY": "🟢", "STRONG_BUY": "🟢", "SELL": "🔴", "HOLD": "🟡", "ERROR": "⚠️"}
        ico = emoji.get(signal_data.get("signal"), "⚪")
        symbol = esc(signal_data.get("symbol", ""))
        sig = esc(signal_data.get("signal", ""))
        price = float(signal_data.get("price", 0) or 0)
        rsi = float(signal_data.get("rsi", 0) or 0)
        macd = float(signal_data.get("macd", 0) or 0)
        confidence = signal_data.get("confidence", 0)

        lines = [
            f"{ico} <b>TRADING SIGNAL</b> {ico}",
            "",
            f"<b>Symbol:</b> {symbol}",
            f"<b>Signal:</b> {sig}",
            f"<b>Price:</b> ${price:.4f}",
            "",
            "<b>Technical Indicators:</b>",
            f"• RSI: {rsi:.1f}",
            f"• MACD: {macd:.4f}",
            f"• Confidence: {esc(confidence)}",
            "",
            "<b>Reasons:</b>",
        ]
        for reason in signal_data.get("reasons", []):
            lines.append(f"• {esc(reason)}")

        if signal_data.get("tp") and signal_data.get("sl"):
            tp = float(signal_data["tp"])
            sl = float(signal_data["sl"])
            tp_pct = float(signal_data.get("tp_pct", 0) or 0)
            sl_pct = float(signal_data.get("sl_pct", 0) or 0)
            rr_ratio = float(signal_data.get("rr_ratio", 1.0) or 1.0)
            ok_emoji = "✅" if rr_ratio >= 1.5 else "⚠️"
            lines.extend([
                "",
                "📊 <b>Dynamic Levels:</b>",
                f"• TP: ${tp:.4f} (+{tp_pct:.1f}%)",
                f"• SL: ${sl:.4f} (-{sl_pct:.1f}%)",
                f"• R:R: {rr_ratio}:1 {ok_emoji}",
            ])

        lines.append("")
        lines.append(f"<b>Time:</b> {esc(signal_data.get('timestamp', _utc_now_str()))}")
        if signal_data.get("signal") in {"BUY", "STRONG_BUY"} and signal_data.get("tp") and signal_data.get("sl"):
            lines.append("")
            lines.append("⚡ <b>Auto-execution enabled</b>")
        return self.send_message("\n".join(lines))

    def send_position_opened(self, position: dict[str, Any]) -> dict[str, Any] | None:
        tp_type = "📊" if position.get("tp_dynamic") else "⚙️"
        lines = [
            f"💼 <b>POSITION OPENED</b> {tp_type}",
            "",
            f"<b>Symbol:</b> {esc(position['symbol'])}",
            f"<b>Type:</b> {esc(position['type'])}",
            f"<b>Entry:</b> ${float(position['entry_price']):.4f}",
            f"<b>Size:</b> ${float(position['size_usd']):.2f} ({float(position['quantity']):.4f} coins)",
            f"<b>Margin:</b> ${float(position.get('margin', 0)):.2f}",
            f"<b>Leverage:</b> {esc(position.get('leverage', 1))}x",
            "",
            "<b>Targets:</b>",
            f"• TP: ${float(position['take_profit']):.4f} {tp_type}",
            f"• SL: ${float(position['stop_loss']):.4f}",
            f"• Liq~: ${float(position.get('liquidation_price', 0)):.4f}",
        ]
        if position.get("rr_ratio"):
            lines.append(f"<b>R:R Ratio:</b> {esc(position['rr_ratio'])}:1")
        lines.append("")
        lines.append(f"<b>Time:</b> {esc(position.get('opened_at', _utc_now_str()))}")
        return self.send_message("\n".join(lines))

    def send_position_closed(self, position: dict[str, Any]) -> dict[str, Any] | None:
        pnl = float(position.get("pnl", 0.0))
        pnl_pct = float(position.get("pnl_pct", 0.0))
        fee = float(position.get("fees_paid", 0.0))
        sign = "+" if pnl >= 0 else ""
        ico = "✅" if pnl > 0 else "❌"
        lines = [
            f"{ico} <b>POSITION CLOSED</b>",
            "",
            f"<b>Symbol:</b> {esc(position['symbol'])}",
            f"<b>Exit:</b> ${float(position['exit_price']):.4f}",
            f"<b>Reason:</b> {esc(position['close_reason'])}",
            "",
            f"<b>PnL (net):</b> {sign}${pnl:.4f} ({sign}{pnl_pct:.2f}% on margin)",
            f"<b>Fees:</b> ${fee:.4f}",
            "",
            f"<b>Duration:</b> {esc(position.get('opened_at', ''))} → {esc(position.get('exit_time', ''))}",
        ]
        return self.send_message("\n".join(lines))

    def send_portfolio_summary(self, summary: dict[str, Any]) -> dict[str, Any] | None:
        pnl = float(summary.get("total_pnl", 0.0))
        pnl_pct = float(summary.get("total_pnl_pct", 0.0))
        sign = "+" if pnl >= 0 else ""
        ico = "✅" if pnl >= 0 else "❌"
        win_rate = (summary["winning_trades"] / max(summary["total_trades"], 1)) * 100
        lines = [
            "📊 <b>PORTFOLIO SUMMARY</b>",
            "",
            "<b>Capital:</b>",
            f"• Initial: ${float(summary['initial_capital']):.2f}",
            f"• Current: ${float(summary['current_capital']):.2f}",
            f"• PnL: {ico} {sign}${pnl:.2f} ({sign}{pnl_pct:.2f}%)",
            "",
            "<b>Positions:</b>",
            f"• Open: {esc(summary['open_positions'])}",
            f"• Total Trades: {esc(summary['total_trades'])}",
            f"• Winners: {esc(summary['winning_trades'])}",
            f"• Losers: {esc(summary['losing_trades'])}",
            f"• Win Rate: {win_rate:.1f}%",
            "",
            f"<b>Time:</b> {esc(_utc_now_str())}",
        ]
        return self.send_message("\n".join(lines))

    def send_error(self, error_message: str) -> dict[str, Any] | None:
        text = f"⚠️ <b>ERROR ALERT</b>\n\n{esc(error_message)}\n\n<b>Time:</b> {esc(_utc_now_str())}"
        return self.send_message(text)

    def send_positions(self, positions: dict[str, Any]) -> dict[str, Any] | None:
        if not positions:
            return self.send_message(
                "📭 <b>NO OPEN POSITIONS</b>\n\nNo active trades.\nWaiting for new signals..."
            )

        lines = ["📊 <b>OPEN POSITIONS</b>", "", f"Total: {len(positions)} position(s)", ""]
        for symbol, pos in positions.items():
            data = pos.to_dict() if hasattr(pos, "to_dict") else pos
            ico = "🟢" if data["type"] == "BUY" else "🔴"
            entry = float(data["entry_price"])
            size_usd = float(data["size_usd"])
            qty = float(data["quantity"])
            tp = float(data["take_profit"])
            sl = float(data["stop_loss"])
            liq = float(data.get("liquidation_price", 0))
            lines.extend([
                f"{ico} <b>{esc(symbol)}</b>",
                f"Type: {esc(data['type'])}",
                f"Entry: ${entry:.4f}",
                f"Size: ${size_usd:.2f} ({qty:.4f} coins)",
                f"TP: ${tp:.4f} | SL: ${sl:.4f}",
                f"Lev: {esc(data.get('leverage', 1))}x | Liq~: ${liq:.4f}",
                f"Opened: {esc(data['opened_at'])}",
                "",
            ])
        return self.send_message("\n".join(lines))

    def send_pnl(self, summary: dict[str, Any]) -> dict[str, Any] | None:
        pnl = float(summary.get("total_pnl", 0.0))
        pnl_pct = float(summary.get("total_pnl_pct", 0.0))
        sign = "+" if pnl >= 0 else ""
        ico = "✅" if pnl >= 0 else "❌"
        win_rate = (summary["winning_trades"] / max(summary["total_trades"], 1)) * 100
        lines = [
            "💰 <b>P&amp;L SUMMARY</b>",
            "",
            "<b>Capital:</b>",
            f"• Initial: ${float(summary['initial_capital']):.2f}",
            f"• Current: ${float(summary['current_capital']):.2f}",
            f"• Locked: ${float(summary['locked_capital']):.2f} 🔒",
            f"• Available: ${float(summary['available_capital']):.2f} 💵",
            f"• Total P&amp;L: {ico} {sign}${pnl:.2f} ({sign}{pnl_pct:.2f}%)",
            "",
            "<b>Trading Stats:</b>",
            f"• Total Trades: {esc(summary['total_trades'])}",
            f"• Winners: {esc(summary['winning_trades'])} ✅",
            f"• Losers: {esc(summary['losing_trades'])} ❌",
            f"• Win Rate: {win_rate:.1f}%",
        ]
        if summary.get("open_positions", 0) > 0:
            lines.append(f"• Open Positions: {esc(summary['open_positions'])} 📊")
        lines.append("")
        lines.append(f"<b>Time:</b> {esc(_utc_now_str())}")
        return self.send_message("\n".join(lines))

    def send_risk_alert(self, alert_type: str, message: str) -> dict[str, Any] | None:
        ico = "⚠️" if alert_type == "warning" else "🚨"
        text = (
            f"{ico} <b>RISK ALERT</b>\n\n"
            f"<b>Type:</b> {esc(alert_type.upper())}\n\n"
            f"{esc(message)}\n\n"
            f"<b>Time:</b> {esc(_utc_now_str())}"
        )
        return self.send_message(text)

    def send_control_response(self, command: str, status: bool, message: str) -> dict[str, Any] | None:
        ico = "✅" if status else "❌"
        return self.send_message(f"{ico} <b>{esc(command.upper())}</b>\n\n{esc(message)}")

    def send_trailing_stop_update(self, update_data: dict[str, Any]) -> dict[str, Any] | None:
        old_sl = float(update_data["old_sl"])
        new_sl = float(update_data["new_sl"])
        text = (
            "📊 <b>TRAILING STOP UPDATE</b>\n\n"
            f"<b>Symbol:</b> {esc(update_data['symbol'])}\n"
            f"<b>Old SL:</b> ${old_sl:.4f}\n"
            f"<b>New SL:</b> ${new_sl:.4f}\n\n"
            "<i>Profit locked automatically.</i>"
        )
        return self.send_message(text)


if __name__ == "__main__":  # pragma: no cover
    import logging_config

    logging_config.setup_logging()
    bot = TelegramBot()
    info = bot.get_me()
    logger.info("Bot info: %s", info)
