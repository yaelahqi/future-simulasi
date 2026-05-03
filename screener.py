"""
Crypto Screener Module.

Scans the market for the best trading opportunities, ranking coins by signal
strength, volume, and momentum. Reuses a shared ccxt instance with the
SignalGenerator to avoid duplicate rate limiters.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import ccxt
import pandas as pd
import pandas_ta_compat as ta

from config import EXCHANGE_ID, RSI_OVERBOUGHT, RSI_OVERSOLD, TIMEFRAME
from tp_sl_calculator import calculate_dynamic_tp_sl

logger = logging.getLogger(__name__)

# Stablecoin base symbols to exclude from screening / auto-trading
STABLECOIN_BASES: set[str] = {
    "USDT", "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "EUR",
    "USDD", "USDP", "SUSD", "GUSD", "USDe", "USD1", "PYUSD",
    "AEUR", "EURI", "CUSD", "CEUR",
}


def _make_exchange(exchange_id: str = EXCHANGE_ID):
    return getattr(ccxt, exchange_id)({"enableRateLimit": True})


class CryptoScreener:
    def __init__(self, min_volume_usd: float = 1_000_000, exchange: Any | None = None) -> None:
        self.exchange = exchange if exchange is not None else _make_exchange()
        self.min_volume_usd = min_volume_usd
        self.top_coins: list[dict[str, Any]] = []

    def get_top_coins_by_volume(self, limit: int = 50, quote: str = "USDT") -> list[dict[str, Any]]:
        try:
            tickers = self.exchange.fetch_tickers()
        except Exception as exc:
            logger.warning("Error fetching tickers: %s", exc)
            return []

        filtered: list[dict[str, Any]] = []
        for symbol, ticker in tickers.items():
            if not symbol.endswith(f"/{quote}"):
                continue
            base = symbol.replace(f"/{quote}", "")
            if base in STABLECOIN_BASES:
                continue
            volume_usd = ticker.get("quoteVolume") or 0
            if volume_usd < self.min_volume_usd:
                continue
            filtered.append({
                "symbol": symbol,
                "price": ticker.get("last", 0) or 0,
                "volume_24h": volume_usd,
                "change_24h": ticker.get("percentage", 0) or 0,
                "high_24h": ticker.get("high", 0) or 0,
                "low_24h": ticker.get("low", 0) or 0,
            })

        filtered.sort(key=lambda x: x["volume_24h"], reverse=True)
        self.top_coins = filtered[:limit]
        return self.top_coins

    @staticmethod
    def calculate_score(df: pd.DataFrame) -> int:
        """Composite score in [-7, +7] (RSI ±2, MA ±1, MACD ±1, vol +1, mom ±1)."""
        score = 0

        # Read the closed candle to align with signal generator.
        latest = df.iloc[-1]
        prev_close = df["close"].iloc[-5] if len(df) >= 5 else df["close"].iloc[0]

        rsi = latest["rsi"]
        if rsi < RSI_OVERSOLD:
            score += 2
        elif rsi < 40:
            score += 1
        elif rsi > RSI_OVERBOUGHT:
            score -= 2
        elif rsi > 60:
            score -= 1

        if latest["close"] > latest["ma_20"]:
            score += 1
        else:
            score -= 1

        if latest["macd"] > latest["macd_signal"]:
            score += 1
        else:
            score -= 1

        if latest["volume"] > latest["vol_sma"] * 1.5:
            score += 1

        momentum = (latest["close"] - prev_close) / prev_close if prev_close else 0
        if momentum > 0.05:
            score += 1
        elif momentum < -0.05:
            score -= 1

        return int(score)

    def analyze_coin(self, symbol: str) -> dict[str, Any]:
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=101)
            if not ohlcv:
                return {"symbol": symbol, "error": "no data", "score": 0, "signal": "ERROR"}

            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            # Drop the in-progress candle for closed-bar indicators.
            if len(df) > 1:
                df = df.iloc[:-1].reset_index(drop=True)

            df["rsi"] = ta.rsi(df["close"], length=14)
            df["ma_20"] = ta.sma(df["close"], length=20)
            df["ma_50"] = ta.sma(df["close"], length=50)
            macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
            df["macd"] = macd["MACD_12_26_9"]
            df["macd_signal"] = macd["MACDs_12_26_9"]
            df["vol_sma"] = ta.sma(df["volume"], length=20)
            bbands = ta.bbands(df["close"], length=20)
            if bbands is not None:
                df["bb_upper"] = bbands["BBU_20_2.0"]
                df["bb_lower"] = bbands["BBL_20_2.0"]

            score = self.calculate_score(df)
            latest = df.iloc[-1]
            current_price = float(latest["close"])

            signal = "BUY" if score >= 2 else ("SELL" if score <= -2 else "HOLD")
            levels = calculate_dynamic_tp_sl(df, current_price, signal)

            return {
                "symbol": symbol,
                "price": current_price,
                "rsi": float(latest["rsi"]),
                "macd": float(latest["macd"]),
                "macd_signal": float(latest["macd_signal"]),
                "volume_24h": float(latest["volume"]),
                "score": score,
                "signal": signal,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "tp": levels["tp"],
                "sl": levels["sl"],
                "rr_ratio": levels["rr_ratio"],
                "tp_pct": levels["tp_pct"],
                "sl_pct": levels["sl_pct"],
            }

        except Exception as exc:
            logger.warning("analyze_coin(%s) failed: %s", symbol, exc)
            return {"symbol": symbol, "error": str(exc), "score": 0, "signal": "ERROR"}

    def scan_market(self, limit: int = 20, min_score: int = 1) -> list[dict[str, Any]]:
        logger.info("Scanning market...")
        top_coins = self.get_top_coins_by_volume(limit=limit)
        if not top_coins:
            logger.info("No coins found with sufficient volume")
            return []
        logger.info("Found %d coins with volume > $%s", len(top_coins), f"{self.min_volume_usd:,.0f}")

        results: list[dict[str, Any]] = []
        for i, coin in enumerate(top_coins, 1):
            logger.debug("[%d/%d] Analyzing %s", i, limit, coin["symbol"])
            analysis = self.analyze_coin(coin["symbol"])
            if "error" not in analysis:
                analysis["volume_24h_usd"] = coin["volume_24h"]
                analysis["change_24h"] = coin["change_24h"]
                results.append(analysis)

        results.sort(key=lambda x: x["score"], reverse=True)
        return [r for r in results if r["score"] >= min_score]

    def get_top_picks(self, limit: int = 5, min_score: int = 2) -> list[dict[str, Any]]:
        scanned = self.scan_market(limit=50, min_score=min_score)
        return scanned[:limit]


if __name__ == "__main__":  # pragma: no cover
    import logging_config
    logging_config.setup_logging()
    s = CryptoScreener(min_volume_usd=1_000_000)
    picks = s.get_top_picks(limit=10, min_score=1)
    for r in picks:
        logger.info(
            "%s @ $%.4f rsi=%.1f score=%s signal=%s",
            r["symbol"], r["price"], r["rsi"], r["score"], r["signal"],
        )
