"""
Signal Generator Module.

Technical analysis: RSI, MA, MACD, Bollinger Bands, Volume.
Generates BUY/STRONG_BUY/SELL/HOLD signals using *closed* candles to avoid
repainting against the still-forming bar.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import ccxt
import pandas as pd
import pandas_ta_compat as ta

from config import EXCHANGE_ID, RSI_OVERBOUGHT, RSI_OVERSOLD, SYMBOLS, TIMEFRAME
from tp_sl_calculator import calculate_dynamic_tp_sl

logger = logging.getLogger(__name__)


def _make_exchange(exchange_id: str = EXCHANGE_ID):
    return getattr(ccxt, exchange_id)({"enableRateLimit": True})


class SignalGenerator:
    def __init__(self, exchange: Any | None = None) -> None:
        # Allow caller to inject a shared ccxt instance to avoid duplicate
        # rate limiters across modules.
        self.exchange = exchange if exchange is not None else _make_exchange()

    def fetch_ohlcv(self, symbol: str, timeframe: str = TIMEFRAME, limit: int = 100) -> pd.DataFrame | None:
        """Fetch OHLCV bars and drop the in-progress candle.

        ccxt returns the still-forming candle at index -1; we strip it to
        prevent indicators that read ``iloc[-1]`` from repainting.
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit + 1)
            if not ohlcv:
                return None
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            # Drop the latest (in-progress) candle.
            if len(df) > 1:
                df = df.iloc[:-1].reset_index(drop=True)
            return df
        except Exception as exc:
            logger.warning("Error fetching OHLCV for %s: %s", symbol, exc)
            return None

    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame | None:
        if df is None or len(df) < 50:
            return None

        df = df.copy()
        df["rsi"] = ta.rsi(df["close"], length=14)
        df["ma_20"] = ta.sma(df["close"], length=20)
        df["ma_50"] = ta.sma(df["close"], length=50)
        df["ema_20"] = ta.ema(df["close"], length=20)

        macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd is not None:
            df["macd"] = macd["MACD_12_26_9"]
            df["macd_signal"] = macd["MACDs_12_26_9"]
            df["macd_hist"] = macd["MACDh_12_26_9"]

        bbands = ta.bbands(df["close"], length=20)
        if bbands is not None:
            df["bb_upper"] = bbands["BBU_20_2.0"]
            df["bb_lower"] = bbands["BBL_20_2.0"]

        df["vol_sma"] = ta.sma(df["volume"], length=20)
        return df

    def evaluate_dataframe(self, df: pd.DataFrame, symbol: str = "") -> dict[str, Any]:
        """Pure-dataframe signal evaluation.

        Reads indicators from ``df.iloc[-1]`` and ``df.iloc[-2]`` (assumed to
        be closed candles already). Used by ``generate_signal`` for live and
        by the backtest engine for replay.
        """
        if df is None or len(df) < 2:
            return {"symbol": symbol, "signal": "ERROR", "reason": "Insufficient data"}

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        reasons: list[str] = []
        confidence = 0

        if latest["rsi"] < RSI_OVERSOLD:
            reasons.append(f"RSI oversold ({latest['rsi']:.1f})")
            confidence += 2
        elif latest["rsi"] < 40:
            reasons.append(f"RSI low ({latest['rsi']:.1f})")
            confidence += 1
        elif latest["rsi"] > RSI_OVERBOUGHT:
            reasons.append(f"RSI overbought ({latest['rsi']:.1f})")
            confidence -= 2
        elif latest["rsi"] > 60:
            reasons.append(f"RSI high ({latest['rsi']:.1f})")
            confidence -= 1

        if latest["close"] > latest["ma_20"]:
            if prev["close"] <= prev["ma_20"]:
                reasons.append("Price crossed above MA20")
            else:
                reasons.append("Price above MA20")
            confidence += 1
        elif latest["close"] < latest["ma_20"]:
            if prev["close"] >= prev["ma_20"]:
                reasons.append("Price crossed below MA20")
            else:
                reasons.append("Price below MA20")
            confidence -= 1

        if "macd" in df.columns and "macd_signal" in df.columns:
            if latest["macd"] > latest["macd_signal"]:
                if prev["macd"] <= prev["macd_signal"]:
                    reasons.append("MACD bullish crossover")
                else:
                    reasons.append("MACD bullish")
                confidence += 1
            elif latest["macd"] < latest["macd_signal"]:
                if prev["macd"] >= prev["macd_signal"]:
                    reasons.append("MACD bearish crossover")
                else:
                    reasons.append("MACD bearish")
                confidence -= 1

        if latest["volume"] > latest["vol_sma"] * 1.5:
            reasons.append(f"Volume spike ({latest['volume']/latest['vol_sma']:.1f}x)")
            confidence += 1

        # Momentum (5-candle lookback to align with screener)
        prev_close = df["close"].iloc[-5] if len(df) >= 5 else df["close"].iloc[0]
        momentum = (latest["close"] - prev_close) / prev_close if prev_close else 0
        if momentum > 0.05:
            reasons.append(f"Strong momentum (+{momentum*100:.1f}%)")
            confidence += 1
        elif momentum < -0.05:
            reasons.append(f"Weak momentum ({momentum*100:.1f}%)")
            confidence -= 1

        # Confidence thresholds:
        # >= 3: STRONG_BUY, >= 2: BUY, <= -2: SELL, otherwise HOLD.
        if confidence >= 3:
            signal = "STRONG_BUY"
        elif confidence >= 2:
            signal = "BUY"
        elif confidence <= -2:
            signal = "SELL"
        else:
            signal = "HOLD"

        return _build_signal_dict(symbol, signal, latest, df, reasons, confidence)

    def generate_signal(self, symbol: str) -> dict[str, Any]:
        df = self.fetch_ohlcv(symbol)
        if df is None:
            return {"symbol": symbol, "signal": "ERROR", "reason": "No data"}

        df = self.calculate_indicators(df)
        if df is None:
            return {"symbol": symbol, "signal": "ERROR", "reason": "Insufficient data"}

        return self.evaluate_dataframe(df, symbol)

    def scan_all_symbols(self) -> list[dict[str, Any]]:
        return [self.generate_signal(symbol) for symbol in SYMBOLS]


def _build_signal_dict(
    symbol: str,
    signal: str,
    latest: pd.Series,
    df: pd.DataFrame,
    reasons: list[str],
    confidence: int,
) -> dict[str, Any]:
    """Compose the standard signal payload, including dynamic TP/SL."""
    price = float(latest["close"])
    levels = calculate_dynamic_tp_sl(df, price, signal)
    return {
        "symbol": symbol,
        "signal": signal,
        "price": price,
        "rsi": float(latest["rsi"]),
        "macd": float(latest.get("macd", 0.0) or 0.0),
        "confidence": int(confidence),
        "reasons": reasons,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "tp": levels["tp"],
        "sl": levels["sl"],
        "rr_ratio": levels["rr_ratio"],
        "tp_pct": levels["tp_pct"],
        "sl_pct": levels["sl_pct"],
    }


if __name__ == "__main__":  # pragma: no cover
    import logging_config
    logging_config.setup_logging()
    generator = SignalGenerator()
    for s in generator.scan_all_symbols():
        logger.info("%s: %s @ $%.2f (Confidence: %s)", s["symbol"], s["signal"],
                    s.get("price", 0), s.get("confidence", "n/a"))
