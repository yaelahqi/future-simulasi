"""
Crypto Trading Bot - Main Entry Point
Integrates: Signal Generator + Paper Trader + Telegram Bot
"""

import time
import signal
import sys
from datetime import datetime
from config import (
    SYMBOLS, PAPER_TRADING, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
)
from signal_generator import SignalGenerator
from paper_trader import PaperTrader
from telegram_bot import TelegramBot


class TradingBot:
    def __init__(self):
        self.signal_gen = SignalGenerator()
        self.trader = PaperTrader() if PAPER_TRADING else None
        self.telegram = TelegramBot()
        self.running = True
        self.last_signal_time = {}
        self.scan_interval = 300  # 5 minutes
        
        # Load previous state if exists
        if self.trader:
            self.trader.load_state()
    
    def handle_signals(self, sig, frame):
        """Handle interrupt signals (Ctrl+C)"""
        print("\n🛑 Shutting down bot...")
        self.running = False
    
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
            
            # Execute paper trade
            if signal_type == 'BUY':
                position = self.trader.open_position(
                    symbol, 
                    signal_data['price'], 
                    signal_type
                )
                self.telegram.send_position_opened(position)
                print(f"✅ Opened position: {symbol} @ ${signal_data['price']:.2f}")
    
    def check_open_positions(self):
        """Check and update open positions"""
        if not self.trader:
            return
        
        # Fetch current prices
        current_prices = {}
        for symbol in SYMBOLS:
            try:
                ticker = self.signal_gen.exchange.fetch_ticker(symbol)
                current_prices[symbol] = ticker['last']
            except:
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
        
        while self.running:
            try:
                # Scan for signals
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scanning markets...")
                signals = self.signal_gen.scan_all_symbols()
                
                for signal_data in signals:
                    print(f"  {signal_data['symbol']}: {signal_data['signal']} @ ${signal_data.get('price', 0):.2f}")
                    
                    # Rate limit signals (max 1 per symbol per 15 min)
                    symbol = signal_data['symbol']
                    last_time = self.last_signal_time.get(symbol, 0)
                    if time.time() - last_time < 900:  # 15 minutes
                        continue
                    
                    self.last_signal_time[symbol] = time.time()
                    self.process_signal(signal_data)
                
                # Check open positions
                self.check_open_positions()
                
                # Send periodic summary
                if time.time() - last_summary_time > summary_interval:
                    self.send_summary()
                    last_summary_time = time.time()
                
                # Save state
                if self.trader:
                    self.trader.save_state()
                
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
