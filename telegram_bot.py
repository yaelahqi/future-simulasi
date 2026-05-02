"""
Telegram Bot Module
Sends trading signals and alerts to Telegram
Receives commands from user
"""

import requests
import json
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


class TelegramBot:
    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}"
    
    def send_message(self, text, parse_mode='Markdown'):
        """Send text message to Telegram"""
        url = f"{self.base_url}/sendMessage"
        data = {
            'chat_id': self.chat_id,
            'text': text,
            'parse_mode': parse_mode
        }
        
        try:
            response = requests.post(url, json=data)
            return response.json()
        except Exception as e:
            print(f"Error sending message: {e}")
            return None
    
    def send_signal(self, signal_data):
        """
        Send trading signal alert
        signal_data: dict from SignalGenerator
        """
        emoji = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡', 'ERROR': '⚠️'}
        
        text = f"""
{emoji.get(signal_data['signal'], '⚪')} *TRADING SIGNAL* {emoji.get(signal_data['signal'], '⚪')}

*Symbol:* {signal_data['symbol']}
*Signal:* {signal_data['signal']}
*Price:* ${signal_data.get('price', 0):.2f}

*Technical Indicators:*
• RSI: {signal_data.get('rsi', 0):.1f}
• MACD: {signal_data.get('macd', 0):.4f}
• Confidence: {signal_data.get('confidence', 0)}

*Reasons:*
"""
        
        for reason in signal_data.get('reasons', []):
            text += f"• {reason}\n"
        
        text += f"\n*Time:* {signal_data.get('timestamp', 'N/A')}"
        
        if signal_data['signal'] in ['BUY', 'SELL']:
            text += f"\n\n⚡ *Action Required!* Check your trading bot."
        
        return self.send_message(text)
    
    def send_position_opened(self, position):
        """Send notification when position is opened"""
        text = f"""
💼 *POSITION OPENED*

*Symbol:* {position['symbol']}
*Type:* {position['type']}
*Entry:* ${position['entry_price']:.2f}
*Size:* ${position['size_usd']:.2f} ({position['quantity']:.4f} coins)
*Leverage:* {position.get('leverage', 10)}x

*Targets:*
• TP: ${position['take_profit']:.2f}
• SL: ${position['stop_loss']:.2f}

*Time:* {position['opened_at']}
"""
        return self.send_message(text)
    
    def send_position_closed(self, position):
        """Send notification when position is closed"""
        pnl_emoji = '✅' if position['pnl'] > 0 else '❌'
        pnl_color = '+' if position['pnl'] > 0 else ''
        
        text = f"""
{pnl_emoji} *POSITION CLOSED*

*Symbol:* {position['symbol']}
*Exit:* ${position['exit_price']:.2f}
*Reason:* {position['close_reason']}

*PnL:* {pnl_color}${position['pnl']:.2f} ({pnl_color}{position['pnl_pct']:.2f}%)

*Duration:* {position['opened_at']} → {position['exit_time']}
"""
        return self.send_message(text)
    
    def send_portfolio_summary(self, summary):
        """Send daily/weekly portfolio summary"""
        pnl_emoji = '✅' if summary['total_pnl'] >= 0 else '❌'
        pnl_color = '+' if summary['total_pnl'] >= 0 else ''
        
        win_rate = (summary['winning_trades'] / max(summary['total_trades'], 1)) * 100
        
        text = f"""
📊 *PORTFOLIO SUMMARY*

*Capital:*
• Initial: ${summary['initial_capital']:.2f}
• Current: ${summary['current_capital']:.2f}
• PnL: {pnl_color}${summary['total_pnl']:.2f} ({pnl_color}{summary['total_pnl_pct']:.2f}%)

*Positions:*
• Open: {summary['open_positions']}
• Total Trades: {summary['total_trades']}
• Winning: {summary['winning_trades']}
• Losing: {summary['losing_trades']}
• Win Rate: {win_rate:.1f}%

*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(text)
    
    def send_error(self, error_message):
        """Send error notification"""
        text = f"""
⚠️ *ERROR ALERT*

{error_message}

*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(text)
    
    def get_updates(self, offset=None):
        """Get updates from Telegram"""
        url = f"{self.base_url}/getUpdates"
        params = {'offset': offset, 'timeout': 30} if offset else {'timeout': 30}
        
        try:
            response = requests.get(url, params=params)
            return response.json()
        except Exception as e:
            print(f"Error getting updates: {e}")
            return None
    
    def get_me(self):
        """Get bot info"""
        url = f"{self.base_url}/getMe"
        try:
            response = requests.get(url)
            return response.json()
        except Exception as e:
            print(f"Error getting bot info: {e}")
            return None


# Test function
if __name__ == "__main__":
    bot = TelegramBot()
    
    # Test connection
    me = bot.get_me()
    print(f"Bot: {me}")
    
    # Test message
    bot.send_message("🤖 Trading Bot Test - Connection Successful!")
