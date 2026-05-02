"""
Configuration file for Crypto Trading Bot
Edit these values or use environment variables
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============= TELEGRAM CONFIG =============
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

# ============= EXCHANGE CONFIG =============
EXCHANGE_ID = os.getenv("EXCHANGE_ID", "binance")  # binance, bybit, okx
API_KEY = os.getenv("API_KEY", "")  # Only needed for live trading
API_SECRET = os.getenv("API_SECRET", "")  # Only needed for live trading

# ============= TRADING CONFIG =============
INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", 10.00))  # USD
LEVERAGE = int(os.getenv("LEVERAGE", 10))
MAX_POSITION_SIZE = float(os.getenv("MAX_POSITION_SIZE", 100))  # USD notional

# ============= SYMBOLS TO TRACK =============
SYMBOLS = os.getenv("SYMBOLS", "SOL/USDT,BTC/USDT,ETH/USDT").split(",")

# ============= SIGNAL SETTINGS =============
RSI_OVERBOUGHT = int(os.getenv("RSI_OVERBOUGHT", 70))
RSI_OVERSOLD = int(os.getenv("RSI_OVERSOLD", 30))
MA_PERIOD = int(os.getenv("MA_PERIOD", 20))
TIMEFRAME = os.getenv("TIMEFRAME", "15m")  # 1m, 5m, 15m, 1h, 4h

# ============= PAPER TRADING SETTINGS =============
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", 5.0))  # 5%
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 5.0))  # 5%

# ============= LOG SETTINGS =============
LOG_FILE = os.getenv("LOG_FILE", "logs/trades.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ============= SCREENING SETTINGS =============
SCREENING_ENABLED = os.getenv("SCREENING_ENABLED", "true").lower() == "true"
SCREENING_MIN_VOLUME = float(os.getenv("SCREENING_MIN_VOLUME", 1_000_000))  # $1M min volume
TOP_N_COINS = int(os.getenv("TOP_N_COINS", 10))  # Track top 10 coins
