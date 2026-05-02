"""
Paper Trading Module
Simulates trades without real money
Tracks PnL, positions, and trade history
"""

import json
import os
from datetime import datetime, timedelta
from config import (
    INITIAL_CAPITAL, LEVERAGE, TAKE_PROFIT_PCT, 
    STOP_LOSS_PCT, LOG_FILE, MAX_POSITIONS, MAX_DAILY_LOSS_PCT,
    POSITION_SIZE_PCT, MAX_LEVERAGE
)


class PaperTrader:
    def __init__(self):
        self.initial_capital = INITIAL_CAPITAL
        self.capital = INITIAL_CAPITAL
        self.leverage = min(LEVERAGE, MAX_LEVERAGE)  # Cap leverage
        self.positions = {}
        self.trade_history = []
        self.locked_capital = 0.0  # Capital locked in open positions
        self.daily_pnl = 0.0  # Track daily PnL
        self.last_reset_date = datetime.now().date()
        self.max_positions = MAX_POSITIONS
        self.position_size_pct = POSITION_SIZE_PCT / 100.0
        self.max_daily_loss_pct = MAX_DAILY_LOSS_PCT
        self.ensure_log_dir()
    
    def ensure_log_dir(self):
        """Create logs directory if not exists"""
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    def reset_daily_stats(self):
        """Reset daily PnL if new day"""
        today = datetime.now().date()
        if today > self.last_reset_date:
            self.daily_pnl = 0.0
            self.last_reset_date = today
            print(f"📅 Daily stats reset. New day: {today}")
    
    def can_open_position(self):
        """
        Check if we can open a new position based on risk rules
        Returns: (can_open: bool, reason: str)
        """
        self.reset_daily_stats()
        
        # Check if trading is enabled
        # (Will be set by main bot from Telegram commands)
        
        # Check max positions
        if len(self.positions) >= self.max_positions:
            return False, f"Max positions reached ({self.max_positions})"
        
        # Check daily loss limit
        daily_loss_pct = (self.daily_pnl / self.initial_capital) * 100
        if daily_loss_pct <= -self.max_daily_loss_pct:
            return False, f"Daily loss limit hit ({daily_loss_pct:.1f}% < -{self.max_daily_loss_pct}%)"
        
        # Check available capital
        available = self.capital - self.locked_capital
        if available <= 0:
            return False, f"No available capital (Locked: ${self.locked_capital:.2f})"
        
        return True, "OK"
    
    def update_trailing_stop(self, symbol, current_price):
        """
        Update trailing stop for a position
        Moves stop loss up when price goes in favor
        """
        if symbol not in self.positions:
            return None
        
        position = self.positions[symbol]
        
        if position['type'] == 'BUY':
            # For long positions, trail stop loss upward
            if current_price > position['entry_price']:
                # Calculate profit percentage
                profit_pct = (current_price - position['entry_price']) / position['entry_price']
                
                # If profit > 3%, move SL to breakeven
                if profit_pct >= 0.03:
                    new_sl = position['entry_price'] * 1.001  # Breakeven + tiny buffer
                    if new_sl > position['stop_loss']:
                        old_sl = position['stop_loss']
                        position['stop_loss'] = new_sl
                        position['trailing_stop_active'] = True
                        return {'symbol': symbol, 'old_sl': old_sl, 'new_sl': new_sl, 'type': 'trailing'}
                
                # If profit > 5%, trail at 2% below current price
                elif profit_pct >= 0.05:
                    new_sl = current_price * 0.98  # 2% trailing
                    if new_sl > position['stop_loss']:
                        old_sl = position['stop_loss']
                        position['stop_loss'] = new_sl
                        position['trailing_stop_active'] = True
                        return {'symbol': symbol, 'old_sl': old_sl, 'new_sl': new_sl, 'type': 'trailing'}
        
        else:  # SELL position
            # For short positions, trail stop loss downward
            if current_price < position['entry_price']:
                profit_pct = (position['entry_price'] - current_price) / position['entry_price']
                
                if profit_pct >= 0.03:
                    new_sl = position['entry_price'] * 0.999
                    if new_sl < position['stop_loss']:
                        old_sl = position['stop_loss']
                        position['stop_loss'] = new_sl
                        position['trailing_stop_active'] = True
                        return {'symbol': symbol, 'old_sl': old_sl, 'new_sl': new_sl, 'type': 'trailing'}
                
                elif profit_pct >= 0.05:
                    new_sl = current_price * 1.02
                    if new_sl < position['stop_loss']:
                        old_sl = position['stop_loss']
                        position['stop_loss'] = new_sl
                        position['trailing_stop_active'] = True
                        return {'symbol': symbol, 'old_sl': old_sl, 'new_sl': new_sl, 'type': 'trailing'}
        
        return None
    
    def open_position(self, symbol, entry_price, signal_type='BUY'):
        """
        Open a paper trading position
        Returns: dict with position info or error if risk rules violated
        """
        # Check risk management rules
        can_open, reason = self.can_open_position()
        if not can_open:
            return {
                'error': 'RISK_RULE_VIOLATION',
                'message': reason,
                'symbol': symbol,
                'signal': signal_type
            }
        
        # Check if enough capital
        if self.capital <= 0:
            return {
                'error': 'INSUFFICIENT_CAPITAL',
                'message': f'No capital available. Current: ${self.capital:.2f}',
                'symbol': symbol,
                'signal': signal_type
            }
        
        # Calculate position size based on AVAILABLE capital and risk settings
        available_capital = self.capital - self.locked_capital
        max_position_capital = available_capital * self.position_size_pct  # Risk: only use X% per trade
        position_size = max_position_capital * self.leverage
        quantity = position_size / entry_price
        
        # Calculate margin required (position_size / leverage)
        margin_required = position_size / self.leverage
        
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
            'margin': margin_required,
            'take_profit': take_profit,
            'stop_loss': stop_loss,
            'opened_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'OPEN'
        }
        
        self.positions[symbol] = position
        
        # Lock capital
        self.locked_capital += margin_required
        
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
        
        # Update capital (release margin + PnL)
        margin_released = position.get('margin', position['size_usd'] / self.leverage)
        self.capital += pnl  # PnL added/subtracted
        self.daily_pnl += pnl  # Track daily PnL
        self.locked_capital -= margin_released  # Release locked margin
        
        # Ensure locked_capital doesn't go negative
        if self.locked_capital < 0:
            self.locked_capital = 0.0
        
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
        return {
            'initial_capital': self.initial_capital,
            'current_capital': self.capital,
            'locked_capital': self.locked_capital,
            'available_capital': self.capital - self.locked_capital,
            'total_pnl': self.capital - self.initial_capital,
            'total_pnl_pct': ((self.capital - self.initial_capital) / self.initial_capital) * 100,
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
