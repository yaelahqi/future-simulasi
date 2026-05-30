DESCRIBE WHAT YOU'VE BUILT WITH AGENTS OR AI-DRIVEN WORKFLOWS

1. Core Problem
Bot trading crypto futures tanpa uang sungguhan (paper trading). Mengatasi masalah: trader pemula ingin belajar trading tanpa risiko kehilangan modal, sekaligus memahami bagaimana sistem trading otomatis bekerja.

2. Core Logic Flow
Multi-agent collaboration dengan 3 thread utama:
- Signal Generator: Analisis teknikal RSI, MA, MACD, Bollinger Bands. Generate sinyal BUY/SELL dari candle yang sudah close (bukan repaint). 
- Paper Trader: Simulasi futures dengan model realistis: taker fee 0.04%, slippage 2bps, liquidation, trailing stop. Risk management: max 3 posisi, max daily loss 20%, position sizing 33%.
- Telegram Bot: Kirim alert sinyal ke user, terima perintah /status /balance /positions /trades.

Long-chain reasoning: Screener → Signal → Position → Monitor → TP/SL → Close. Screening interval 30 menit, scan signal 2 menit, position check 15 detik. Dynamic TP/SL berdasarkan teknikal level (Bollinger, ATR).

Backtest engine: Bar-by-bar tanpa lookahead. Hasil backtest top 50 coin: 69% win rate, +5.80% return, Profit Factor 2.21.

Twitter sentiment integration: Module terpisah untuk analisis sentimen crypto via Twitter/X search.

Stack: Python, ccxt, pandas, pandas_ta, Telegram API. Deploy via PM2. All paper trading, no real money.
