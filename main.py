"""
Crypto Trading Bot - Main Entry Point
Integrates: Signal Generator + Paper Trader + Telegram Bot
"""

import time
import signal
import sys
from datetime import datetime
from config import (
    SYMBOLS, PAPER_TRADING, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    SCREENING_ENABLED, SCREENING_MIN_VOLUME, TOP_N_COINS, TRADING_ENABLED
)
from signal_generator import SignalGenerator
from paper_trader import PaperTrader
from telegram_bot import TelegramBot
from screener import CryptoScreener


class TradingBot:
    def __init__(self):
        self.signal_gen = SignalGenerator()
        self.screener = CryptoScreener(min_volume_usd=SCREENING_MIN_VOLUME) if SCREENING_ENABLED else None
        self.trader = PaperTrader() if PAPER_TRADING else None
        self.telegram = TelegramBot()
        self.running = True
        self.last_signal_time = {}
        self.scan_interval = 300  # 5 minutes
        self.active_symbols = list(SYMBOLS) if not SCREENING_ENABLED else []
        self.trading_enabled = TRADING_ENABLED  # Can be toggled via Telegram
        self.last_processed_msg_id = 0
        
        # Load previous state if exists
        if self.trader:
            self.trader.load_state()
    
    def handle_signals(self, sig, frame):
        """Handle interrupt signals (Ctrl+C)"""
        print("\n🛑 Shutting down bot...")
        self.running = False
    
    def handle_telegram_commands(self):
        """Check and handle Telegram commands"""
        try:
            updates = self.telegram.get_updates(offset=self.last_processed_msg_id + 1)
            if not updates or 'result' not in updates:
                return
            
            for update in updates['result']:
                if 'message' not in update or 'text' not in update['message']:
                    continue
                
                chat_id = update['message']['chat']['id']
                text = update['message']['text'].strip()
                message_id = update['message']['message_id']
                
                # Update last processed message ID
                self.last_processed_msg_id = message_id
                
                # Only respond to authorized chat
                if str(chat_id) != str(TELEGRAM_CHAT_ID):
                    continue
                
                # Handle commands (case-insensitive)
                cmd = text.lower()
                
                if cmd in ['/positions', '/pos']:
                    if self.trader:
                        self.telegram.send_positions(self.trader.positions)
                    else:
                        self.telegram.send_message("❌ Paper trading not enabled")
                
                elif cmd in ['/pnl', '/p&l']:
                    if self.trader:
                        summary = self.trader.get_portfolio_summary()
                        self.telegram.send_pnl(summary)
                    else:
                        self.telegram.send_message("❌ Paper trading not enabled")
                
                elif cmd in ['/start', '/help']:
                    help_text = """
🤖 *Crypto Trading Bot Commands*

📊 *Portfolio:*
• /positions - View open positions
• /pnl - View P&L summary
• /status - Portfolio overview

🎮 *Control:*
• /pause - Pause trading (no new positions)
• /resume - Resume trading
• /close SYMBOL - Close specific position (e.g., /close SOL)
• /closeall - Close all positions
• /reset - Reset capital to initial

⚙️ *Bot Info:*
• /start - Start bot
• /help - Show this help

_Status: {}_
_Screening: {}_
_Tracking: {} coin(s)_
""".format(
                        '🟢 Trading' if self.trading_enabled else '🔴 Paused',
                        'Enabled 🔍' if self.screener else 'Disabled ❌',
                        len(self.active_symbols)
                    )
                    self.telegram.send_message(help_text)
                
                elif cmd == '/status':
                    if self.trader:
                        summary = self.trader.get_portfolio_summary()
                        self.telegram.send_portfolio_summary(summary)
                    else:
                        self.telegram.send_message("❌ Paper trading not enabled")
                
                elif cmd == '/pause':
                    self.trading_enabled = False
                    self.telegram.send_control_response(
                        'PAUSE', True,
                        "Trading paused. No new positions will be opened.\n\nExisting positions will continue to be monitored."
                    )
                    print("⏸️ Trading paused")
                
                elif cmd == '/resume':
                    self.trading_enabled = True
                    self.telegram.send_control_response(
                        'RESUME', True,
                        "Trading resumed. Bot will open new positions based on signals."
                    )
                    print("▶️ Trading resumed")
                
                elif cmd.startswith('/close '):
                    if not self.trader:
                        self.telegram.send_message("❌ Paper trading not enabled")
                        continue
                    
                    symbol = text.split(' ', 1)[1].strip().upper()
                    if '/' in symbol:
                        symbol = symbol  # Already has USDT
                    else:
                        symbol = f"{symbol}/USDT"
                    
                    if symbol in self.trader.positions:
                        # Get current price
                        try:
                            ticker = self.signal_gen.exchange.fetch_ticker(symbol)
                            close_result = self.trader.close_position(symbol, ticker['last'], 'MANUAL')
                            self.telegram.send_position_closed(close_result)
                            print(f"✅ Manually closed {symbol}")
                        except Exception as e:
                            self.telegram.send_control_response(
                                'CLOSE', False,
                                f"Error closing position: {str(e)}"
                            )
                    else:
                        self.telegram.send_control_response(
                            'CLOSE', False,
                            f"No open position for {symbol}"
                        )
                
                elif cmd == '/closeall':
                    if not self.trader or not self.trader.positions:
                        self.telegram.send_control_response(
                            'CLOSEALL', False,
                            "No open positions to close"
                        )
                    else:
                        closed_count = 0
                        for symbol in list(self.trader.positions.keys()):
                            try:
                                ticker = self.signal_gen.exchange.fetch_ticker(symbol)
                                self.trader.close_position(symbol, ticker['last'], 'MANUAL')
                                closed_count += 1
                            except:
                                continue
                        
                        self.telegram.send_control_response(
                            'CLOSEALL', True,
                            f"Closed {closed_count} position(s)"
                        )
                        print(f"✅ Closed all {closed_count} positions")
                
                elif cmd == '/reset':
                    if self.trader:
                        # Close all positions first
                        for symbol in list(self.trader.positions.keys()):
                            try:
                                ticker = self.signal_gen.exchange.fetch_ticker(symbol)
                                self.trader.close_position(symbol, ticker['last'], 'RESET')
                            except:
                                continue
                        
                        # Reset capital
                        self.trader.capital = self.trader.initial_capital
                        self.trader.daily_pnl = 0.0
                        self.trader.save_state()
                        
                        self.telegram.send_control_response(
                            'RESET', True,
                            f"Capital reset to ${self.trader.initial_capital:.2f}\n\nAll positions closed."
                        )
                        print(f"🔄 Capital reset to ${self.trader.initial_capital:.2f}")
                    else:
                        self.telegram.send_message("❌ Paper trading not enabled")
                
        except Exception as e:
            print(f"Error handling commands: {e}")
    
    def process_signal(self, signal_data):
        """Process trading signal and execute if needed"""
        symbol = signal_data['symbol']
        signal_type = signal_data['signal']
        
        # Send signal to Telegram
        self.telegram.send_signal(signal_data)
        
        # Skip if HOLD or ERROR
        if signal_type not in ['BUY', 'SELL']:
            return
        
        # Check if we already have a position
        if self.trader:
            if symbol in self.trader.positions:
                print(f"⚠️ Already have position for {symbol}, skipping")
                return
            
            # Execute paper trade with dynamic TP/SL from screening
            if signal_type == 'BUY':
                position = self.trader.open_position(
                    symbol, 
                    signal_data['price'], 
                    signal_type,
                    tp=signal_data.get('tp'),  # Dynamic TP from screening
                    sl=signal_data.get('sl'),  # Dynamic SL from screening
                    rr_ratio=signal_data.get('rr_ratio')  # R:R ratio
                )
                
                # Check if position opened successfully
                if 'error' in position:
                    if position['error'] == 'INSUFFICIENT_CAPITAL':
                        # Send alert about no capital
                        self.telegram.send_message(f"""
⚠️ *INSUFFICIENT CAPITAL*

Signal: {signal_type} {symbol}
Price: ${signal_data['price']:.4f}

{position['message']}

💡 *Action Needed:*
• Reset capital in config
• Or wait for positions to close
""")
                        print(f"❌ Cannot open {symbol}: {position['message']}")
                    
                    elif position['error'] == 'RISK_RULE_VIOLATION':
                        # Send risk alert
                        self.telegram.send_risk_alert('warning', position['message'])
                        print(f"⚠️ Risk rule violation for {symbol}: {position['message']}")
                    
                    else:
                        print(f"❌ Error opening position: {position}")
                else:
                    self.telegram.send_position_opened(position)
                    print(f"✅ Opened position: {symbol} @ ${signal_data['price']:.2f}")
    
    def check_open_positions(self):
        """Check and update open positions (including trailing stops)"""
        if not self.trader:
            return
        
        # Fetch current prices for all active symbols
        current_prices = {}
        for symbol in self.trader.positions.keys():
            try:
                ticker = self.signal_gen.exchange.fetch_ticker(symbol)
                current_prices[symbol] = ticker['last']
                
                # Update trailing stops
                trailing_update = self.trader.update_trailing_stop(symbol, ticker['last'])
                if trailing_update:
                    self.telegram.send_trailing_stop_update(trailing_update)
                    print(f"📊 Trailing stop updated for {symbol}: ${trailing_update['old_sl']:.4f} → ${trailing_update['new_sl']:.4f}")
                    
            except Exception as e:
                print(f"Error fetching price for {symbol}: {e}")
                continue
        
        # Check for TP/SL hits
        closed = self.trader.check_positions(current_prices)
        
        for position in closed:
            self.telegram.send_position_closed(position)
            print(f"✅ Closed position: {position['symbol']} | PnL: ${position['pnl']:.2f}")
    
    def send_summary(self):
        """Send portfolio summary"""
        if self.trader:
            summary = self.trader.get_portfolio_summary()
            self.telegram.send_portfolio_summary(summary)
    
    def send_screening_results(self, picks):
        """Send screening results with dynamic TP/SL to Telegram"""
        if not picks:
            return
        
        text = "🔍 *MARKET SCREENER RESULTS*\n\n"
        text += f"Top {len(picks)} coins ranked by signal strength:\n\n"
        
        for i, pick in enumerate(picks[:5], 1):  # Top 5
            emoji = '🟢' if pick['signal'] == 'BUY' else ('🔴' if pick['signal'] == 'SELL' else '🟡')
            text += f"{i}. {emoji} *{pick['symbol']}*\n"
            text += f"   Price: ${pick['price']:.4f}\n"
            text += f"   RSI: {pick['rsi']:.1f} | Score: {pick['score']}\n"
            text += f"   24h: {pick.get('change_24h', 0):+.2f}%\n"
            
            # Show dynamic TP/SL if available
            if pick.get('tp') and pick.get('sl'):
                text += f"   TP: ${pick['tp']:.4f} (+{pick.get('tp_pct', 0):.1f}%)\n"
                text += f"   SL: ${pick['sl']:.4f} (-{pick.get('sl_pct', 0):.1f}%)\n"
                if pick.get('rr_ratio'):
                    text += f"   R:R: {pick['rr_ratio']}:1 ✅\n"
            
            text += "\n"
        
        text += f"_Scan time: {datetime.now().strftime('%H:%M:%S')}._"
        
        self.telegram.send_message(text)
    
    def run(self):
        """Main bot loop"""
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.handle_signals)
        signal.signal(signal.SIGTERM, self.handle_signals)
        
        # Send startup message
        self.telegram.send_message("""
🚀 *Trading Bot Started!*

*Mode:* Paper Trading
*Symbols:* """ + ", ".join(SYMBOLS) + f"""
*Scan Interval:* {self.scan_interval // 60} min

Monitoring markets...
""")
        
        print("🤖 Trading Bot Started!")
        print(f"📊 Symbols: {', '.join(SYMBOLS)}")
        print(f"📈 Scan Interval: {self.scan_interval // 60} minutes")
        print("Press Ctrl+C to stop\n")
        
        last_summary_time = time.time()
        summary_interval = 3600  # Send summary every hour
        last_screening_time = 0
        screening_interval = 1800  # Screen every 30 minutes
        
        while self.running:
            try:
                # Run market screening if enabled
                if self.screener and time.time() - last_screening_time > screening_interval:
                    print(f"\n🔍 Running market screener...")
                    top_picks = self.screener.get_top_picks(limit=TOP_N_COINS, min_score=1)
                    
                    if top_picks:
                        self.active_symbols = [p['symbol'] for p in top_picks]
                        print(f"✅ Selected {len(self.active_symbols)} coins: {', '.join(self.active_symbols)}")
                        
                        # Send screening results to Telegram
                        self.send_screening_results(top_picks)
                    
                    last_screening_time = time.time()
                
                # Scan for signals on active symbols
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scanning {len(self.active_symbols)} coins...")
                
                for symbol in self.active_symbols:
                    signal_data = self.signal_gen.generate_signal(symbol)
                    print(f"  {signal_data['symbol']}: {signal_data['signal']} @ ${signal_data.get('price', 0):.2f}")
                    
                    # Rate limit signals (max 1 per symbol per 15 min)
                    last_time = self.last_signal_time.get(symbol, 0)
                    if time.time() - last_time < 900:  # 15 minutes
                        continue
                    
                    self.last_signal_time[symbol] = time.time()
                    self.process_signal(signal_data)
                
                # Check open positions (includes trailing stop updates)
                self.check_open_positions()
                
                # Send periodic summary
                if time.time() - last_summary_time > summary_interval:
                    self.send_summary()
                    last_summary_time = time.time()
                
                # Save state
                if self.trader:
                    self.trader.save_state()
                
                # Check Telegram commands
                self.handle_telegram_commands()
                
                # Wait for next scan
                time.sleep(self.scan_interval)
                
            except Exception as e:
                error_msg = f"Error in main loop: {str(e)}"
                print(f"❌ {error_msg}")
                self.telegram.send_error(error_msg)
                time.sleep(60)  # Wait 1 min before retry
        
        # Shutdown
        if self.trader:
            self.trader.save_state()
        
        self.telegram.send_message("🛑 Trading Bot Stopped")
        print("\n✅ Bot stopped. State saved.")


def main():
    """Entry point"""
    # Validate config
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Please configure TELEGRAM_BOT_TOKEN in config.py or .env")
        sys.exit(1)
    
    if TELEGRAM_CHAT_ID == "YOUR_CHAT_ID_HERE":
        print("❌ Please configure TELEGRAM_CHAT_ID in config.py or .env")
        sys.exit(1)
    
    # Start bot
    bot = TradingBot()
    bot.run()


if __name__ == "__main__":
    main()
