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
API_KEY = os.getenv("API_KEY", "")
API_SECRET = os.getenv("API_SECRET", "")
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

# Trading mode:
# normal     = existing TP/SL and trailing behavior
# aggressive = wider TP target + faster trailing stop to let winners run
TRADING_MODE = os.getenv("TRADING_MODE", "normal").strip().lower()
AGGRESSIVE_TP_MULTIPLIER = float(os.getenv("AGGRESSIVE_TP_MULTIPLIER", "2.2"))
AGGRESSIVE_TRAIL_BREAKEVEN_PCT = float(os.getenv("AGGRESSIVE_TRAIL_BREAKEVEN_PCT", "1.5")) / 100.0
AGGRESSIVE_TRAIL_LOCK_PCT = float(os.getenv("AGGRESSIVE_TRAIL_LOCK_PCT", "3.0")) / 100.0
AGGRESSIVE_TRAIL_DISTANCE_PCT = float(os.getenv("AGGRESSIVE_TRAIL_DISTANCE_PCT", "1.2")) / 100.0

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
MAX_SAME_DIRECTION = int(os.getenv("MAX_SAME_DIRECTION", "2"))
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "20.0"))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", "33.0"))
MAX_LEVERAGE = int(os.getenv("MAX_LEVERAGE", "10"))
TRADING_ENABLED = _bool("TRADING_ENABLED", "true")

# Real trading safety layer. Default stays paper/simulation.
REAL_TRADING_ENABLED = _bool("REAL_TRADING_ENABLED", "false")
REAL_CONFIRM_FILE = os.getenv("REAL_CONFIRM_FILE", os.path.abspath("REAL_TRADING_CONFIRMED"))
REAL_MAX_POSITIONS = int(os.getenv("REAL_MAX_POSITIONS", "2"))
REAL_MAX_SAME_DIRECTION = int(os.getenv("REAL_MAX_SAME_DIRECTION", "2"))
REAL_POSITION_SIZE_PCT = float(os.getenv("REAL_POSITION_SIZE_PCT", "10.0"))
REAL_MAX_DAILY_LOSS_PCT = float(os.getenv("REAL_MAX_DAILY_LOSS_PCT", "5.0"))
REAL_MAX_LEVERAGE = int(os.getenv("REAL_MAX_LEVERAGE", "3"))
REAL_MIN_BALANCE_USDT = float(os.getenv("REAL_MIN_BALANCE_USDT", "10.0"))
REAL_MIN_NOTIONAL_USDT = float(os.getenv("REAL_MIN_NOTIONAL_USDT", "5.0"))
REAL_REQUIRE_MANUAL_CONFIRM = _bool("REAL_REQUIRE_MANUAL_CONFIRM", "true")
REAL_ORDER_TYPE = os.getenv("REAL_ORDER_TYPE", "market").strip().lower()

# Funding-rate guard for perpetual futures. Decimal rate: 0.0005 = 0.05%.
# Blocks entries only when funding is adverse for trade direction:
#   LONG/BUY pays when funding > threshold
#   SHORT/SELL pays when funding < -threshold
FUNDING_RATE_CHECK = _bool("FUNDING_RATE_CHECK", "true")
MAX_ADVERSE_FUNDING_RATE = float(os.getenv("MAX_ADVERSE_FUNDING_RATE", "0.0005"))

# BTC regime guard: if BTC 4H EMA9 < EMA21, new LONG/BUY entries are blocked.
BTC_REGIME_CHECK = _bool("BTC_REGIME_CHECK", "true")
BTC_REGIME_SYMBOL = os.getenv("BTC_REGIME_SYMBOL", "BTC/USDT")
BTC_REGIME_TIMEFRAME = os.getenv("BTC_REGIME_TIMEFRAME", "4h")

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
