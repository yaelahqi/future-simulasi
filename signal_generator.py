"""
Signal Generator Module
Technical Analysis: RSI, MA, MACD, Volume
Generates BUY/SELL/HOLD signals
"""

import ccxt
import pandas as pd
import pandas_ta as ta
from datetime import datetime
from config import (
    EXCHANGE_ID, SYMBOLS, TIMEFRAME,
    RSI_OVERBOUGHT, RSI_OVERSOLD, MA_PERIOD
)


class SignalGenerator:
    def __init__(self):
        # No API keys needed for public data (prices, OHLCV)
        self.exchange = getattr(ccxt, EXCHANGE_ID)({
            'enableRateLimit': True,
            # API keys only needed for private endpoints (orders, balances)
            # 'apiKey': API_KEY,  # Not needed for paper trading
            # 'secret': API_SECRET,  # Not needed for paper trading
        })
    
    def fetch_ohlcv(self, symbol, timeframe=TIMEFRAME, limit=100):
        """Fetch candlestick data from exchange"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            return None
    
    def calculate_indicators(self, df):
        """Calculate technical indicators"""
        if df is None or len(df) < 50:
            return None
        
        # RSI
        df['rsi'] = ta.rsi(df['close'], length=14)
        
        # Moving Averages
        df['ma_20'] = ta.sma(df['close'], length=20)
        df['ma_50'] = ta.sma(df['close'], length=50)
        df['ema_20'] = ta.ema(df['close'], length=20)
        
        # MACD
        macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
        df['macd'] = macd['MACD_12_26_9']
        df['macd_signal'] = macd['MACDs_12_26_9']
        df['macd_hist'] = macd['MACDh_12_26_9']
        
        # Bollinger Bands
        bbands = ta.bbands(df['close'], length=20)
        df['bb_upper'] = bbands['BBU_20_2.0']
        df['bb_lower'] = bbands['BBL_20_2.0']
        
        # Volume SMA
        df['vol_sma'] = ta.sma(df['volume'], length=20)
        
        return df
    
    def generate_signal(self, symbol):
        """
        Generate trading signal based on technical indicators
        Returns: dict with signal info
        """
        df = self.fetch_ohlcv(symbol)
        if df is None:
            return {'symbol': symbol, 'signal': 'ERROR', 'reason': 'No data'}
        
        df = self.calculate_indicators(df)
        if df is None:
            return {'symbol': symbol, 'signal': 'ERROR', 'reason': 'Insufficient data'}
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        signal = 'HOLD'
        reasons = []
        confidence = 0
        
        # RSI Signal
        if latest['rsi'] < RSI_OVERSOLD:
            reasons.append(f"RSI oversold ({latest['rsi']:.1f})")
            confidence += 1
        elif latest['rsi'] > RSI_OVERBOUGHT:
            reasons.append(f"RSI overbought ({latest['rsi']:.1f})")
            confidence -= 1
        
        # MA Crossover
        if latest['close'] > latest['ma_20'] and prev['close'] <= prev['ma_20']:
            reasons.append("Price crossed above MA20")
            confidence += 1
        elif latest['close'] < latest['ma_20'] and prev['close'] >= prev['ma_20']:
            reasons.append("Price crossed below MA20")
            confidence -= 1
        
        # MACD Crossover
        if latest['macd'] > latest['macd_signal'] and prev['macd'] <= prev['macd_signal']:
            reasons.append("MACD bullish crossover")
            confidence += 1
        elif latest['macd'] < latest['macd_signal'] and prev['macd'] >= prev['macd_signal']:
            reasons.append("MACD bearish crossover")
            confidence -= 1
        
        # Volume Spike
        if latest['volume'] > latest['vol_sma'] * 2:
            reasons.append(f"Volume spike ({latest['volume']/latest['vol_sma']:.1f}x)")
            confidence += 1
        
        # Determine final signal with better thresholds
        # Score >= 3: STRONG BUY (100% position)
        # Score == 2: BUY (can open position)
        # Score 1 to -1: HOLD (wait)
        # Score <= -2: SELL/AVOID
        if confidence >= 3:
            signal = 'STRONG_BUY'  # High confidence
        elif confidence >= 2:
            signal = 'BUY'  # Good entry
        elif confidence <= -2:
            signal = 'SELL'
        else:
            signal = 'HOLD'
        
        # Calculate dynamic TP/SL based on recent price action
        tp, sl, rr_ratio = self.calculate_dynamic_tp_sl(df, latest['close'])
        
        return {
            'symbol': symbol,
            'signal': signal,
            'price': latest['close'],
            'rsi': latest['rsi'],
            'macd': latest['macd'],
            'confidence': confidence,
            'reasons': reasons,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'tp': tp,
            'sl': sl,
            'rr_ratio': rr_ratio,
            'tp_pct': ((tp - latest['close']) / latest['close']) * 100 if tp else 0,
            'sl_pct': ((latest['close'] - sl) / latest['close']) * 100 if sl else 0
        }
    
    def calculate_dynamic_tp_sl(self, df, current_price):
        """
        Calculate dynamic TP/SL based on technical levels
        Returns: (tp, sl, rr_ratio)
        """
        try:
            # Get recent highs/lows (last 20 candles)
            recent_high = df['high'].tail(20).max()
            recent_low = df['low'].tail(20).min()
            
            # Bollinger Bands
            bb_upper = df['bb_upper'].iloc[-1]
            bb_lower = df['bb_lower'].iloc[-1]
            
            # ATR for volatility-based stops
            atr = ta.atr(df['high'], df['low'], df['close'], length=14).iloc[-1]
            
            # For BUY signals:
            # TP = resistance (recent high or BB upper)
            # SL = support (recent low or BB lower)
            tp = min(recent_high, bb_upper)  # Conservative TP
            sl = max(recent_low, bb_lower)   # Conservative SL
            
            # Ensure minimum R:R of 1:1.5
            risk = current_price - sl
            reward = tp - current_price
            
            if risk <= 0 or reward <= 0:
                # Fallback to ATR-based levels
                tp = current_price * 1.03  # 3% TP
                sl = current_price * 0.97  # 3% SL
                rr_ratio = 1.0
            else:
                rr_ratio = reward / risk
                
                # Adjust if R:R too low
                if rr_ratio < 1.5:
                    # Widen TP or tighten SL
                    sl = current_price - (reward / 1.5)
                    if sl > recent_low * 0.98:  # Don't go too low
                        tp = current_price + (risk * 1.5)
                    rr_ratio = 1.5
            
            return round(tp, 4), round(sl, 4), round(rr_ratio, 2)
            
        except Exception as e:
            print(f"Error calculating TP/SL: {e}")
            # Fallback
            tp = current_price * 1.05
            sl = current_price * 0.95
            return round(tp, 4), round(sl, 4), 1.0
    
    def scan_all_symbols(self):
        """Scan all configured symbols and return signals"""
        signals = []
        for symbol in SYMBOLS:
            signal = self.generate_signal(symbol)
            signals.append(signal)
        return signals


# Test function
if __name__ == "__main__":
    generator = SignalGenerator()
    signals = generator.scan_all_symbols()
    for s in signals:
        print(f"{s['symbol']}: {s['signal']} @ ${s['price']:.2f} (Confidence: {s['confidence']})")
