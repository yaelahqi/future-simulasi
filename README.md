# 🚀 Crypto Trading Bot

Automated crypto trading bot with Telegram alerts and paper trading. Perfect for testing strategies before using real money.

## ✨ Features

- 📊 **Technical Analysis** - RSI, MACD, Moving Averages, Volume
- 📱 **Telegram Alerts** - Real-time signal notifications
- 📝 **Paper Trading** - Test strategies risk-free
- 🔄 **Auto Execution** - Open/close positions based on signals
- 📈 **Portfolio Tracking** - PnL, win rate, trade history
- 🔍 **Market Screener** - Auto-scan and select best coins
- 🚀 **Auto-Compounding** - Profits automatically increase position size
- 💵 **Capital Management** - Track locked vs available capital
- 🛡️ **Risk Management** - Max positions, daily loss limit, leverage cap
- 📊 **Trailing Stop Loss** - Auto-lock profits as price moves in favor
- 🎮 **Telegram Control** - Pause/resume trading, close positions remotely
- ⚙️ **Configurable** - Easy setup via environment variables

## 📋 Requirements

- Python 3.8+
- Telegram account
- Internet connection

## 🚀 Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/yaelahqi/future-simulasi.git
cd future-simulasi
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

### Portfolio Commands

| Command | Aliases | Description |
|---------|---------|-------------|
| `/positions` | `/pos` | View open positions |
| `/pnl` | `/p&l` | View P&L summary |
| `/status` | - | Portfolio overview |

### Control Commands

| Command | Description |
|---------|-------------|
| `/pause` | Pause trading (no new positions) |
| `/resume` | Resume trading |
| `/close SYMBOL` | Close specific position (e.g., `/close SOL`) |
| `/closeall` | Close all open positions |
| `/reset` | Reset capital to initial (closes all positions) |

### Info Commands

| Command | Aliases | Description |
|---------|---------|-------------|
| `/start` | - | Start bot |
| `/help` | - | Show all commands |

## 🔧 Configuration

### Key Settings

#### Capital & Leverage

| Variable | Default | Description |
|----------|---------|-------------|
| `INITIAL_CAPITAL` | 10.00 | Starting capital (USD) |
| `LEVERAGE` | 10 | Trading leverage |
| `MAX_LEVERAGE` | 10 | Hard cap on leverage |
| `PAPER_TRADING` | true | Simulate trades |

#### Risk Management

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_POSITIONS` | 3 | Max concurrent positions |
| `MAX_DAILY_LOSS_PCT` | 20.0 | Stop trading if -20% in a day |
| `POSITION_SIZE_PCT` | 100.0 | % of capital per trade |
| `TRADING_ENABLED` | true | Global trading toggle |

#### Take Profit / Stop Loss

| Variable | Default | Description |
|----------|---------|-------------|
| `TAKE_PROFIT_PCT` | 5.0 | Take profit percentage |
| `STOP_LOSS_PCT` | 5.0 | Stop loss percentage |

#### Market Screening

| Variable | Default | Description |
|----------|---------|-------------|
| `SCREENING_ENABLED` | true | Auto-scan market for best coins |
| `SCREENING_MIN_VOLUME` | 1000000 | Min 24h volume ($1M) |
| `TOP_N_COINS` | 10 | Number of coins to track |
| `TIMEFRAME` | 15m | Chart timeframe |
| `SYMBOLS` | SOL,BTC,ETH | Coins to track (if screening disabled) |

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

## 🛡️ Risk Management Features

### Max Positions
Limits concurrent open positions to avoid overexposure:
```env
MAX_POSITIONS=3  # Max 3 positions at once
```

### Daily Loss Limit
Stops trading if daily loss exceeds threshold:
```env
MAX_DAILY_LOSS_PCT=20.0  # Stop if -20% in a day
```

### Position Sizing
Control how much capital per trade:
```env
POSITION_SIZE_PCT=100.0  # Use 100% of available capital
```

### Leverage Cap
Hard limit on leverage:
```env
MAX_LEVERAGE=10  # Never exceed 10x
```

### Trailing Stop Loss
Automatically locks in profits:
- **3% profit**: SL moves to breakeven
- **5% profit**: SL trails at 2% below current price

**Example:**
```
Entry: $84.50
Initial SL: $80.00 (-5%)

Price hits $88.00 (+4.1%):
→ SL moves to $84.58 (breakeven)

Price hits $92.00 (+8.8%):
→ SL moves to $90.16 (2% trailing)

Price drops to $90.16:
→ Position closes with +6.7% profit (not -5% loss!)
```

---

## 🚀 Deployment Guide (24/7 Running)

### Option 1: PM2 (Recommended)

**PM2** is a production process manager that keeps your bot running 24/7 with auto-restart.

#### Step 1: Install PM2

```bash
# Via npm (Node.js required)
npm install -g pm2

# Verify installation
pm2 --version
```

#### Step 2: Start Bot with PM2

```bash
cd future-simulasi

# Start bot
pm2 start main.py --name crypto-bot --interpreter python3

# Or with custom config
pm2 start main.py --name crypto-bot --interpreter python3 -- --config production.env
```

#### Step 3: Save PM2 Configuration

```bash
# Save current process list
pm2 save

# Setup PM2 to start on system boot
pm2 startup

# Run the generated command (copy from output)
sudo env PATH=$PATH:/usr/bin pm2 startup systemd -u your_username --hp /home/your_username
```

#### Step 4: Monitor Bot

```bash
# Check status
pm2 status

# View real-time logs
pm2 logs crypto-bot

# Monitor CPU/Memory
pm2 monit

# Describe process details
pm2 describe crypto-bot
```

#### Step 5: Common PM2 Commands

```bash
# Restart bot
pm2 restart crypto-bot

# Stop bot
pm2 stop crypto-bot

# Delete from PM2
pm2 delete crypto-bot

# Restart all processes
pm2 restart all

# View all logs
pm2 logs

# Flush logs
pm2 flush
```

#### PM2 Ecosystem File (Optional)

Create `ecosystem.config.js` for advanced configuration:

```javascript
module.exports = {
  apps: [{
    name: 'crypto-bot',
    script: 'main.py',
    interpreter: 'python3',
    cwd: '/path/to/future-simulasi',
    env: {
      PYTHONUNBUFFERED: '1',
    },
    error_file: './logs/pm2-error.log',
    out_file: './logs/pm2-out.log',
    log_file: './logs/pm2-combined.log',
    time: true,
    autorestart: true,
    max_memory_restart: '500M',
    watch: false,
  }]
};
```

Start with ecosystem file:
```bash
pm2 start ecosystem.config.js
```

---

### Option 2: Screen (Quick Test)

```bash
# Start screen session
screen -S crypto-bot

# Run bot
python main.py

# Detach (bot keeps running)
Ctrl+A, then D

# Reattach
screen -r crypto-bot

# Kill session
screen -S crypto-bot -X quit
```

---

### Option 3: Systemd (VPS/Server)

Create service file:

```bash
sudo nano /etc/systemd/system/crypto-bot.service
```

Paste:
```ini
[Unit]
Description=Crypto Trading Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/future-simulasi
ExecStart=/usr/bin/python3 /path/to/future-simulasi/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable & start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable crypto-bot
sudo systemctl start crypto-bot
sudo systemctl status crypto-bot
```

View logs:
```bash
sudo journalctl -u crypto-bot -f
```

---

## 🐛 Troubleshooting

### Bot not sending messages
- Check `TELEGRAM_BOT_TOKEN` is correct
- Check `TELEGRAM_CHAT_ID` is correct
- Make sure bot is not blocked

### No signals generated
- Check internet connection
- Verify exchange API is accessible
- Adjust RSI thresholds in config
- Increase `SCREENING_MIN_VOLUME` if no coins found

### Import errors
```bash
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

### PM2: Bot keeps restarting
```bash
# Check error logs
pm2 logs crypto-bot --err

# Check memory usage
pm2 monit

# Increase max memory in ecosystem.config.js
```

### PM2: Bot won't start
```bash
# Test manually first
python main.py

# Check Python path
which python3

# Update ecosystem.config.js with correct paths
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
