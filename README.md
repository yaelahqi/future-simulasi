# 🚀 Crypto Trading Bot

Automated crypto trading bot with Telegram alerts and paper trading. Perfect for testing strategies before using real money.

## ✨ Features

- 📊 **Technical Analysis** - RSI, MACD, Moving Averages, Volume
- 📱 **Telegram Alerts** - Real-time signal notifications
- 📝 **Paper Trading** - Test strategies risk-free
- 🔄 **Auto Execution** - Open/close positions based on signals
- 📈 **Portfolio Tracking** - PnL, win rate, trade history
- ⚙️ **Configurable** - Easy setup via environment variables

## 📋 Requirements

- Python 3.8+
- Telegram account
- Internet connection

## 🚀 Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/crypto-trading-bot.git
cd crypto-trading-bot
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Create Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Follow instructions to create bot
4. Copy the **Bot Token**

### 4. Get Your Chat ID

1. Search for `@userinfobot` in Telegram
2. Start the bot and send any message
3. Copy your **Chat ID**

### 5. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` file:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Trading settings
INITIAL_CAPITAL=10.00
LEVERAGE=10
PAPER_TRADING=true

# Symbols to track
SYMBOLS=SOL/USDT,BTC/USDT,ETH/USDT
```

### 6. Run the Bot

```bash
python main.py
```

## 📱 Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Start bot |
| `/status` | Portfolio summary |
| `/help` | Show help |

## 🔧 Configuration

### Key Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `INITIAL_CAPITAL` | 10.00 | Starting capital (USD) |
| `LEVERAGE` | 10 | Trading leverage |
| `PAPER_TRADING` | true | Simulate trades |
| `TAKE_PROFIT_PCT` | 5.0 | Take profit percentage |
| `STOP_LOSS_PCT` | 5.0 | Stop loss percentage |
| `TIMEFRAME` | 15m | Chart timeframe |
| `SYMBOLS` | SOL,BTC,ETH | Coins to track |

### Signal Logic

**BUY Signal (Confidence ≥ 2):**
- RSI < 30 (oversold)
- Price crosses above MA20
- MACD bullish crossover
- Volume spike (>2x average)

**SELL Signal (Confidence ≤ -2):**
- RSI > 70 (overbought)
- Price crosses below MA20
- MACD bearish crossover
- Volume spike

## 📊 Project Structure

```
crypto-trading-bot/
├── main.py              # Main bot runner
├── signal_generator.py  # Technical analysis
├── paper_trader.py      # Paper trading engine
├── telegram_bot.py      # Telegram integration
├── config.py            # Configuration
├── requirements.txt     # Dependencies
├── .env                 # Environment variables
└── logs/                # Trade logs
```

## 📈 Example Output

### Signal Alert (Telegram)
```
🟢 TRADING SIGNAL 🟢

Symbol: SOL/USDT
Signal: BUY
Price: $84.50

Technical Indicators:
• RSI: 28.5
• MACD: 0.1234
• Confidence: 3

Reasons:
• RSI oversold (28.5)
• Price crossed above MA20
• Volume spike (2.5x)

Time: 2026-05-02 21:00:00

⚡ Action Required! Check your trading bot.
```

### Position Opened
```
💼 POSITION OPENED

Symbol: SOL/USDT
Type: BUY
Entry: $84.50
Size: $100.00 (1.1834 coins)
Leverage: 10x

Targets:
• TP: $88.73
• SL: $80.28

Time: 2026-05-02 21:00:00
```

### Position Closed
```
✅ POSITION CLOSED

Symbol: SOL/USDT
Exit: $88.73
Reason: TAKE_PROFIT

PnL: +$5.00 (+50.00%)

Duration: 2026-05-02 21:00:00 → 2026-05-02 23:30:00
```

## ⚠️ Disclaimer

**This bot is for educational purposes only.**

- Paper trading uses fake money
- Do NOT use for real trading without thorough testing
- Cryptocurrency trading is high risk
- Past performance does not guarantee future results
- Always do your own research

## 🐛 Troubleshooting

### Bot not sending messages
- Check `TELEGRAM_BOT_TOKEN` is correct
- Check `TELEGRAM_CHAT_ID` is correct
- Make sure bot is not blocked

### No signals generated
- Check internet connection
- Verify exchange API is accessible
- Adjust RSI thresholds in config

### Import errors
```bash
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

## 📝 License

MIT License - Feel free to modify and use!

## 🤝 Contributing

Pull requests welcome! Please:
1. Fork the repo
2. Create feature branch
3. Commit changes
4. Push to branch
5. Open Pull Request

## 📞 Support

Issues? Open a GitHub issue or contact me.

---

**Happy Trading! 🚀**
