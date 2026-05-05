"""
Configuration file for Crypto Trading Bot
Edit values via environment variables (.env file).
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


# ============= TELEGRAM CONFIG =============
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

# ============= EXCHANGE CONFIG =============
EXCHANGE_ID = os.getenv("EXCHANGE_ID", "binance")  # e.g. binance, bybit, okx
# Market type for ccxt: "future" (USDT-M perpetuals) matches the simulator's
# fee/leverage/liquidation model. Override to "spot" only for testing on
# spot OHLCV. Exchanges that don't honour defaultType ignore this value.
MARKET_TYPE = os.getenv("MARKET_TYPE", "future")

# ============= TRADING CONFIG =============
INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", "10.00"))  # USD
LEVERAGE = int(os.getenv("LEVERAGE", "10"))

# ============= SYMBOLS TO TRACK =============
SYMBOLS = [s.strip() for s in os.getenv("SYMBOLS", "SOL/USDT,BTC/USDT,ETH/USDT").split(",") if s.strip()]

# ============= SIGNAL SETTINGS =============
RSI_OVERBOUGHT = int(os.getenv("RSI_OVERBOUGHT", "70"))
RSI_OVERSOLD = int(os.getenv("RSI_OVERSOLD", "30"))
MA_PERIOD = int(os.getenv("MA_PERIOD", "20"))
TIMEFRAME = os.getenv("TIMEFRAME", "15m")

# ============= PAPER TRADING SETTINGS =============
PAPER_TRADING = _bool("PAPER_TRADING", "true")
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "5.0"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "5.0"))

# Trading costs (futures realism)
# Binance USDT-M futures default taker fee: 0.04% per side. Round-trip ~0.08%.
TAKER_FEE_PCT = float(os.getenv("TAKER_FEE_PCT", "0.04"))  # % per fill
SLIPPAGE_BPS = float(os.getenv("SLIPPAGE_BPS", "2.0"))  # basis points (2 bps = 0.02%)

# ============= LOG SETTINGS =============
LOG_FILE = os.getenv("LOG_FILE", "logs/trades.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# State persistence (use absolute path so cwd doesn't matter)
STATE_FILE = os.path.abspath(os.getenv("STATE_FILE", "paper_trader_state.json"))

# ============= SCREENING SETTINGS =============
SCREENING_ENABLED = _bool("SCREENING_ENABLED", "true")
SCREENING_MIN_VOLUME = float(os.getenv("SCREENING_MIN_VOLUME", "1000000"))  # $1M min volume
TOP_N_COINS = int(os.getenv("TOP_N_COINS", "10"))

# ============= RISK MANAGEMENT =============
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "3"))
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "20.0"))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", "33.0"))
MAX_LEVERAGE = int(os.getenv("MAX_LEVERAGE", "10"))
TRADING_ENABLED = _bool("TRADING_ENABLED", "true")

# ============= LOOP INTERVALS (seconds) =============
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "120"))  # signal scan period
POSITION_CHECK_INTERVAL = int(os.getenv("POSITION_CHECK_INTERVAL", "15"))  # near-real-time TP/SL checks
SCREENING_INTERVAL = int(os.getenv("SCREENING_INTERVAL", "1800"))  # 30 min full screening
SCREENING_COOLDOWN = int(os.getenv("SCREENING_COOLDOWN", "300"))  # cooldown between re-screen triggers
SUMMARY_INTERVAL = int(os.getenv("SUMMARY_INTERVAL", "3600"))  # periodic summary
BLACKLIST_DURATION = int(os.getenv("BLACKLIST_DURATION", "1800"))  # 30 min after SL
COMMAND_INTERVAL = int(os.getenv("COMMAND_INTERVAL", "5"))
SIGNAL_RATE_LIMIT = int(os.getenv("SIGNAL_RATE_LIMIT", "1800"))  # 30 min between signals/symbol

# Network
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))  # seconds for requests calls
