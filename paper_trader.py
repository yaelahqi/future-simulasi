"""
Paper Trading Module
Simulates trades without real money
Tracks PnL, positions, and trade history
"""

import json
import os
from datetime import datetime
from config import (
    INITIAL_CAPITAL, LEVERAGE, TAKE_PROFIT_PCT, 
    STOP_LOSS_PCT, LOG_FILE
)


class PaperTrader:
    def __init__(self):
        self.capital = INITIAL_CAPITAL
        self.leverage = LEVERAGE
        self.positions = {}
        self.trade_history = []
        self.ensure_log_dir()
    
    def ensure_log_dir(self):
        """Create logs directory if not exists"""
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    def open_position(self, symbol, entry_price, signal_type='BUY'):
        """
        Open a paper trading position
        Returns: dict with position info
        """
        position_size = self.capital * self.leverage
        quantity = position_size / entry_price
        
        # Calculate TP and SL
        if signal_type == 'BUY':
            take_profit = entry_price * (1 + TAKE_PROFIT_PCT / 100)
            stop_loss = entry_price * (1 - STOP_LOSS_PCT / 100)
        else:  # SELL
            take_profit = entry_price * (1 - TAKE_PROFIT_PCT / 100)
            stop_loss = entry_price * (1 + STOP_LOSS_PCT / 100)
        
        position = {
            'symbol': symbol,
            'type': signal_type,
            'entry_price': entry_price,
            'quantity': quantity,
            'size_usd': position_size,
            'take_profit': take_profit,
            'stop_loss': stop_loss,
            'opened_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'OPEN'
        }
        
        self.positions[symbol] = position
        
        # Log the trade
        self.log_trade('OPEN', position)
        
        return position
    
    def close_position(self, symbol, exit_price, reason='MANUAL'):
        """
        Close a paper trading position
        Returns: dict with PnL info
        """
        if symbol not in self.positions:
            return {'error': 'No open position'}
        
        position = self.positions[symbol]
        
        # Calculate PnL
        if position['type'] == 'BUY':
            pnl = (exit_price - position['entry_price']) * position['quantity']
        else:  # SELL
            pnl = (position['entry_price'] - exit_price) * position['quantity']
        
        pnl_pct = (pnl / self.capital) * 100
        
        # Update capital
        self.capital += pnl
        
        # Create closed position record
        closed_position = {
            **position,
            'exit_price': exit_price,
            'exit_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'close_reason': reason,
            'status': 'CLOSED'
        }
        
        # Remove from open positions
        del self.positions[symbol]
        
        # Add to history
        self.trade_history.append(closed_position)
        
        # Log the trade
        self.log_trade('CLOSE', closed_position)
        
        return closed_position
    
    def check_positions(self, current_prices):
        """
        Check all open positions for TP/SL hits
        Returns: list of closed positions
        """
        closed = []
        
        for symbol, position in list(self.positions.items()):
            if symbol not in current_prices:
                continue
            
            current_price = current_prices[symbol]
            
            # Check take profit
            if position['type'] == 'BUY':
                if current_price >= position['take_profit']:
                    result = self.close_position(symbol, current_price, 'TAKE_PROFIT')
                    closed.append(result)
                elif current_price <= position['stop_loss']:
                    result = self.close_position(symbol, current_price, 'STOP_LOSS')
                    closed.append(result)
            else:  # SELL
                if current_price <= position['take_profit']:
                    result = self.close_position(symbol, current_price, 'TAKE_PROFIT')
                    closed.append(result)
                elif current_price >= position['stop_loss']:
                    result = self.close_position(symbol, current_price, 'STOP_LOSS')
                    closed.append(result)
        
        return closed
    
    def get_portfolio_summary(self):
        """Get current portfolio summary"""
        open_pnl = 0
        
        for symbol, position in self.positions.items():
            # Calculate unrealized PnL (will be updated with real prices)
            pass
        
        return {
            'initial_capital': INITIAL_CAPITAL,
            'current_capital': self.capital,
            'total_pnl': self.capital - INITIAL_CAPITAL,
            'total_pnl_pct': ((self.capital - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100,
            'open_positions': len(self.positions),
            'total_trades': len(self.trade_history),
            'winning_trades': len([t for t in self.trade_history if t.get('pnl', 0) > 0]),
            'losing_trades': len([t for t in self.trade_history if t.get('pnl', 0) <= 0])
        }
    
    def log_trade(self, action, position):
        """Log trade to file"""
        log_entry = {
            'action': action,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            **position
        }
        
        with open(LOG_FILE, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def save_state(self, filename='paper_trader_state.json'):
        """Save current state to file"""
        state = {
            'capital': self.capital,
            'positions': self.positions,
            'trade_history': self.trade_history
        }
        with open(filename, 'w') as f:
            json.dump(state, f, indent=2)
    
    def load_state(self, filename='paper_trader_state.json'):
        """Load state from file"""
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                state = json.load(f)
                self.capital = state.get('capital', INITIAL_CAPITAL)
                self.positions = state.get('positions', {})
                self.trade_history = state.get('trade_history', [])


# Test function
if __name__ == "__main__":
    trader = PaperTrader()
    
    # Test opening position
    pos = trader.open_position('SOL/USDT', 84.50, 'BUY')
    print(f"Opened: {pos}")
    
    # Test portfolio summary
    summary = trader.get_portfolio_summary()
    print(f"Portfolio: {summary}")
    
    # Test closing position
    result = trader.close_position('SOL/USDT', 88.00, 'TAKE_PROFIT')
    print(f"Closed: {result}")
