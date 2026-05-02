"""
Crypto Screener Module
Scans market for best trading opportunities
Ranks coins by signal strength, volume, and momentum
"""

import ccxt
import pandas as pd
import pandas_ta as ta
from datetime import datetime
from config import (
    EXCHANGE_ID, TIMEFRAME, 
    RSI_OVERBOUGHT, RSI_OVERSOLD
)
from tp_sl_calculator import calculate_dynamic_tp_sl


def _calculate_dynamic_tp_sl_old(df, current_price):
    """
    Calculate dynamic Take Profit and Stop Loss based on technical levels
    
    Returns:
        dict: tp, sl, rr_ratio (risk/reward)
    """
    if df is None or len(df) < 50:
        # Fallback to fixed percentages if insufficient data
        return {
            'tp': current_price * 1.05,
            'sl': current_price * 0.95,
            'rr_ratio': 1.0
        }
    
    # Calculate indicators if not present
    if 'bb_upper' not in df.columns:
        bbands = ta.bbands(df['close'], length=20)
        df['bb_upper'] = bbands['BBU_20_2.0']
        df['bb_lower'] = bbands['BBL_20_2.0']
    
    if 'atr' not in df.columns:
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    # Support/Resistance from recent highs/lows (20 periods)
    resistance = df['high'].rolling(window=20).max().iloc[-1]
    support = df['low'].rolling(window=20).min().iloc[-1]
    
    # Bollinger Bands
    bb_upper = df['bb_upper'].iloc[-1]
    bb_lower = df['bb_lower'].iloc[-1]
    
    # ATR for volatility-based stops
    atr = df['atr'].iloc[-1]
    
    # Take Profit: Use resistance or BB upper (whichever is closer)
    tp_candidates = [resistance, bb_upper]
    tp = min([x for x in tp_candidates if x > current_price], default=current_price * 1.05)
    
    # Stop Loss: Use support, BB lower, or ATR-based (whichever is highest)
    sl_candidates = [support, bb_lower, current_price - (atr * 2)]
    sl = max([x for x in sl_candidates if x < current_price], default=current_price * 0.95)
    
    # Calculate distances
    tp_distance = tp - current_price
    sl_distance = current_price - sl
    
    # Ensure minimum R:R of 1:1.5
    min_rr = 1.5
    if tp_distance < sl_distance * min_rr:
        # Adjust SL tighter to meet R:R requirement
        sl = current_price - (tp_distance / min_rr)
        sl_distance = current_price - sl
    
    # Calculate final R:R ratio
    rr_ratio = tp_distance / sl_distance if sl_distance > 0 else 0
    
    return {
        'tp': round(tp, 4),
        'sl': round(sl, 4),
        'rr_ratio': round(rr_ratio, 2),
        'tp_distance_pct': round((tp_distance / current_price) * 100, 2),
        'sl_distance_pct': round((sl_distance / current_price) * 100, 2),
        'resistance': round(resistance, 4),
        'support': round(support, 4)
    }


class CryptoScreener:
    def __init__(self, min_volume_usd=1_000_000):
        """
        Initialize screener
        
        Args:
            min_volume_usd: Minimum 24h volume in USD (default: $1M)
        """
        self.exchange = getattr(ccxt, EXCHANGE_ID)({
            'enableRateLimit': True,
        })
        self.min_volume_usd = min_volume_usd
        self.top_coins = []
    
    def get_top_coins_by_volume(self, limit=50, quote='USDT'):
        """
        Get top coins by 24h trading volume
        
        Returns:
            list: Top coin symbols sorted by volume
        """
        try:
            # Fetch all tickers
            tickers = self.exchange.fetch_tickers()
            
            # Filter by quote currency and minimum volume
            filtered = []
            for symbol, ticker in tickers.items():
                if not symbol.endswith(f'/{quote}'):
                    continue
                
                volume_usd = ticker.get('quoteVolume', 0)
                if volume_usd < self.min_volume_usd:
                    continue
                
                filtered.append({
                    'symbol': symbol,
                    'price': ticker.get('last', 0),
                    'volume_24h': volume_usd,
                    'change_24h': ticker.get('percentage', 0),
                    'high_24h': ticker.get('high', 0),
                    'low_24h': ticker.get('low', 0)
                })
            
            # Sort by volume and take top N
            filtered.sort(key=lambda x: x['volume_24h'], reverse=True)
            self.top_coins = filtered[:limit]
            
            return self.top_coins
            
        except Exception as e:
            print(f"Error fetching tickers: {e}")
            return []
    
    def calculate_score(self, df):
        """
        Calculate composite score for a coin
        
        Scoring:
        - RSI oversold: +2 points
        - RSI overbought: -2 points
        - Price > MA20: +1 point
        - MACD bullish: +1 point
        - Volume spike: +1 point
        - Strong momentum: +1 point
        
        Returns:
            int: Score (-5 to +5)
        """
        score = 0
        
        # RSI Score
        rsi = df['rsi'].iloc[-1]
        if rsi < RSI_OVERSOLD:
            score += 2
        elif rsi < 40:
            score += 1
        elif rsi > RSI_OVERBOUGHT:
            score -= 2
        elif rsi > 60:
            score -= 1
        
        # MA Trend
        if df['close'].iloc[-1] > df['ma_20'].iloc[-1]:
            score += 1
        else:
            score -= 1
        
        # MACD
        if df['macd'].iloc[-1] > df['macd_signal'].iloc[-1]:
            score += 1
        else:
            score -= 1
        
        # Volume
        if df['volume'].iloc[-1] > df['vol_sma'].iloc[-1] * 1.5:
            score += 1
        
        # Momentum (5-period)
        momentum = (df['close'].iloc[-1] - df['close'].iloc[-5]) / df['close'].iloc[-5]
        if momentum > 0.05:  # +5%
            score += 1
        elif momentum < -0.05:  # -5%
            score -= 1
        
        return score
    
    def analyze_coin(self, symbol):
        """
        Analyze a single coin with dynamic TP/SL
        
        Returns:
            dict: Analysis results with TP/SL levels
        """
        try:
            # Fetch OHLCV
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Calculate indicators
            df['rsi'] = ta.rsi(df['close'], length=14)
            df['ma_20'] = ta.sma(df['close'], length=20)
            df['ma_50'] = ta.sma(df['close'], length=50)
            
            macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
            df['macd'] = macd['MACD_12_26_9']
            df['macd_signal'] = macd['MACDs_12_26_9']
            
            df['vol_sma'] = ta.sma(df['volume'], length=20)
            
            # Calculate score
            score = self.calculate_score(df)
            
            # Get latest data
            latest = df.iloc[-1]
            current_price = latest['close']
            
            # Calculate dynamic TP/SL using shared module
            levels = calculate_dynamic_tp_sl(df, current_price, 'BUY' if score >= 2 else 'HOLD')
            
            return {
                'symbol': symbol,
                'price': current_price,
                'rsi': latest['rsi'],
                'macd': latest['macd'],
                'macd_signal': latest['macd_signal'],
                'volume_24h': latest['volume'],
                'score': score,
                'signal': 'BUY' if score >= 2 else ('SELL' if score <= -2 else 'HOLD'),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                # Dynamic levels (from shared module)
                'tp': levels['tp'],
                'sl': levels['sl'],
                'rr_ratio': levels['rr_ratio'],
                'tp_pct': levels['tp_pct'],
                'sl_pct': levels['sl_pct']
            }
            
        except Exception as e:
            return {
                'symbol': symbol,
                'error': str(e),
                'score': 0,
                'signal': 'ERROR'
            }
    
    def scan_market(self, limit=20, min_score=1):
        """
        Scan market and return top coins
        
        Args:
            limit: Number of coins to analyze
            min_score: Minimum score threshold
        
        Returns:
            list: Ranked coins with analysis
        """
        print(f"🔍 Scanning market...")
        
        # Get top coins by volume
        top_coins = self.get_top_coins_by_volume(limit=limit)
        if not top_coins:
            print("❌ No coins found with sufficient volume")
            return []
        
        print(f"Found {len(top_coins)} coins with volume > ${self.min_volume_usd:,.0f}")
        
        # Analyze each coin
        results = []
        for i, coin in enumerate(top_coins, 1):
            print(f"[{i}/{limit}] Analyzing {coin['symbol']}...")
            
            analysis = self.analyze_coin(coin['symbol'])
            if analysis and 'error' not in analysis:
                analysis['volume_24h_usd'] = coin['volume_24h']
                analysis['change_24h'] = coin['change_24h']
                results.append(analysis)
        
        # Sort by score (highest first)
        results.sort(key=lambda x: x['score'], reverse=True)
        
        # Filter by minimum score
        filtered = [r for r in results if r['score'] >= min_score]
        
        return filtered
    
    def get_top_picks(self, limit=5, min_score=2):
        """
        Get top trading picks
        
        Args:
            limit: Number of picks to return
            min_score: Minimum score threshold
        
        Returns:
            list: Top picks
        """
        scanned = self.scan_market(limit=50, min_score=min_score)
        return scanned[:limit]
    
    def print_results(self, results):
        """Print screening results in table format"""
        if not results:
            print("No coins found matching criteria")
            return
        
        print("\n" + "="*80)
        print(f"{'SYMBOL':<15} {'PRICE':<12} {'RSI':<8} {'SCORE':<8} {'SIGNAL':<10} {'24H %':<10}")
        print("="*80)
        
        for r in results:
            signal_emoji = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡'}.get(r['signal'], '⚪')
            print(f"{r['symbol']:<15} ${r['price']:<11.4f} {r['rsi']:<8.1f} {r['score']:<8} {signal_emoji} {r['signal']:<8} {r.get('change_24h', 0):>+8.2f}%")
        
        print("="*80)
        print(f"Total coins analyzed: {len(results)}")
        print(f"Buy signals: {len([r for r in results if r['signal'] == 'BUY'])}")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")


# Test function
if __name__ == "__main__":
    screener = CryptoScreener(min_volume_usd=1_000_000)
    
    # Get top picks
    picks = screener.get_top_picks(limit=10, min_score=1)
    
    # Print results
    screener.print_results(picks)
