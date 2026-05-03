# 🚀 Crypto Trading Bot

Automated crypto trading bot with Telegram alerts and paper trading. Perfect for testing strategies before using real money.

## ✨ Features

- 📊 **Technical Analysis** — RSI, MACD, Moving Averages, Bollinger Bands, Volume (computed on **closed** candles, not the still-forming bar)
- 📱 **Telegram Alerts** — Real-time signal notifications with HTML escaping
- 📝 **Paper Trading** — Risk-free simulation with **realistic taker fee, slippage, and isolated-margin liquidation**
- 🔄 **Auto Execution** — Long-only entries triggered by signals
- 📈 **Portfolio Tracking** — PnL, win rate, trade history (persisted across restarts)
- 🔍 **Market Screener** — Auto-scan and select best coins by volume + signal score
- 🚀 **Compounding** — Position size scales with TOTAL equity (winning trades grow the per-trade base)
- 💵 **Capital Management** — Free vs locked capital tracked under a thread lock
- 🛡️ **Risk Management** — Max positions, daily loss limit (vs start-of-day equity), leverage cap, post-SL blacklist
- 📊 **Trailing Stop Loss** — Auto-lock profits, ratchet-only (never loosens)
- 🎮 **Telegram Control** — Pause/resume, close-one, close-all (with confirmation), reset (with confirmation), manual screen
- ⚙️ **Configurable** — Every loop interval, fee, slippage, etc. tunable via env

## ⚠️ Disclaimer

This project is a **paper-trading simulator for educational purposes**. The simulated taker fee, slippage, and liquidation models are simplifications and **do not capture funding rates, partial fills, exchange outages, or maintenance-margin tiers**. Real-money trading carries serious risk of loss. **Do not** treat green simulated PnL as a guarantee of live performance.

## 📋 Requirements

- Python 3.9+
- Telegram account
- Internet connection

## 🚀 Quick Start

### ⚡ No API Key Needed!

**This bot uses PAPER TRADING only** - no Binance API key required! It fetches public price data without authentication.

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

> **Note:** No exchange API key needed! Bot uses public price data only.

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
| `/closeall confirm` | Close all open positions (requires `confirm` token) |
| `/reset confirm` | Reset capital to initial — closes all positions (requires `confirm`) |
| `/screen` | Manual screening trigger (get fresh signals) |

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
| `POSITION_SIZE_PCT` | 33.0 | % of capital per trade (33% allows ~3 concurrent positions) |
| `TRADING_ENABLED` | true | Global trading toggle |

#### Take Profit / Stop Loss

> **Note:** TP/SL now calculated dynamically from market levels (support/resistance). Fixed percentages below are fallback only.

| Variable | Default | Description |
|----------|---------|-------------|
| `TAKE_PROFIT_PCT` | 5.0 | Fallback if dynamic levels unavailable |
| `STOP_LOSS_PCT` | 5.0 | Fallback if dynamic levels unavailable |

#### Market Screening

| Variable | Default | Description |
|----------|---------|-------------|
| `SCREENING_ENABLED` | true | Auto-scan market for best coins |
| `SCREENING_MIN_VOLUME` | 1000000 | Min 24h volume ($1M) |
| `TOP_N_COINS` | 10 | Number of coins to track |
| `TIMEFRAME` | 15m | Chart timeframe |
| `SYMBOLS` | SOL,BTC,ETH | Coins to track (if screening disabled) |

### Signal Logic

Confidence is the sum of contributions from each indicator (`+1` bullish / `-1` bearish, RSI extreme weighs `±2` in the screener).

**STRONG_BUY** — confidence `≥ 3` (used for the most aggressive entries)
**BUY** — confidence `2`
**HOLD** — confidence in `[-1, +1]`
**SELL** — confidence `≤ -2` (logged but **not acted on** — bot is long-only)

Indicators considered:
- RSI < 30 oversold (`+1`) / RSI > 70 overbought (`-1`)
- Price crossing above MA20 (`+1`) / below MA20 (`-1`)
- MACD bullish crossover (`+1`) / bearish crossover (`-1`)
- Volume spike `>2x` average (`+1`)

### Realism Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `TAKER_FEE_PCT` | 0.04 | Taker fee per fill, % (Binance USDT-M default) |
| `SLIPPAGE_BPS` | 2.0 | Slippage in basis points applied on each fill |

Liquidation is approximated as `entry × (1 − 1/leverage + 0.005)` for longs (isolated margin, ~0.5% maintenance buffer). Stop-loss is automatically tightened above the liquidation price at order-open time.

## 📊 Project Structure

```
future-simulasi/
├── main.py              # Bot runner & loops
├── signal_generator.py  # Technical analysis (uses closed candles)
├── paper_trader.py      # Thread-safe paper engine w/ fees + slippage + liq
├── screener.py          # Market screener (volume + composite score)
├── tp_sl_calculator.py  # Dynamic TP/SL with min 1.5 R:R
├── telegram_bot.py      # Telegram integration (HTML, timeouts)
├── logging_config.py    # Centralized logging setup
├── config.py            # All configuration via env vars
├── requirements.txt     # Pinned runtime dependencies
├── requirements-dev.txt # Dev tooling (pytest, ruff)
├── pyproject.toml       # Lint/test config
├── tests/               # Unit tests (pytest)
├── .env                 # Your environment (gitignored)
└── logs/                # Trade logs and bot.log
```

## 🧪 Tests & Lint

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
ruff check .
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

## 📊 Dynamic TP/SL from Screening

Bot calculates **Take Profit** and **Stop Loss** dynamically using:

```
1. Recent highs/lows (20 candles)
2. Bollinger Bands
3. ATR volatility
4. Minimum R:R 1:1.5 enforced
```

### Fresh TP/SL on Entry

When opening a position, bot **re-calculates TP/SL** with fresh market data:

```
Screening: 07:30 - XRP @ $1.3955, TP: $1.3962, SL: $1.3950
Signal:    07:45 - XRP @ $1.4000, TP: $1.4010, SL: $1.3985 (fresh!)
```

**Benefits:**
- ✅ Accurate entry price
- ✅ Current market levels
- ✅ No stale data
- ✅ Consistent R:R ratio

## ⏱️ Position Check Interval

Bot checks all open positions **every 2 minutes** against real market prices:

- ✅ **TP/SL Detection** - Avg 1 min delay
- ✅ **Trailing Stops** - Updated every 2 min
- ✅ **60 API calls/hour** - Sustainable rate
- ✅ **Balanced** - Fast enough, not spammy

## 🔄 Auto Re-Screening on Position Close

When a position closes (TP/SL hit), bot automatically:

```
1. Checks if slot available (< MAX_POSITIONS)
2. Checks cooldown (5 min since last screening)
3. Blacklists coin if SL hit (30 min avoid re-entry)
4. Triggers fresh screening
5. Opens best new signal automatically
```

**Benefits:**
- ✅ No stale signals (always fresh data)
- ✅ Capital always working (slots filled quickly)
- ✅ No missed opportunities
- ✅ Smart blacklist (avoid re-entering losers)

**Manual Trigger:**
```
/screen  # Get fresh signals anytime
```

---

### How It Works:

```
1. Screening analyzes OHLCV data
2. Calculates support/resistance from:
   • 20-period highs/lows
   • Bollinger Bands
   • ATR (volatility)
3. Sets TP at resistance levels
4. Sets SL at support levels
5. Ensures minimum R:R ratio of 1:1.5
```

### Example Output:

```
🟢 SOL/USDT
   Price: $84.50
   TP: $88.00 (+4.1%)
   SL: $80.00 (-5.3%)
   R:R: 1:1.3 ✅
```

### Benefits:

- ✅ **Market-Based** - TP/SL from actual levels
- ✅ **Per-Coin** - Different for each coin
- ✅ **Volatility Adjusted** - Wider for high vol
- ✅ **Optimal R:R** - Minimum 1:1.5 enforced

---

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

## ❓ FAQ

### Do I need a Binance API key?
**No!** This bot uses paper trading only and fetches public price data without authentication. API keys are only needed if you enable live trading in the future.

### Is my capital safe?
**Yes!** This is paper trading (simulation) only. No real money is used. Your actual funds remain safe in your wallet/exchange.

### Can I switch to live trading later?
**Yes!** Add your API keys to `.env` and enable live trading mode. Make sure to disable withdrawals on your API key for security.

### Which exchanges are supported?
**Any exchange supported by CCXT:** Binance, Bybit, OKX, Kraken, etc. Just change `EXCHANGE_ID` in `.env`.

### How accurate is paper trading?
**Very accurate!** Bot uses real market prices from exchanges. The only difference is no real order execution.

---

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
