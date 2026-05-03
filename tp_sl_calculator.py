"""
Dynamic TP/SL Calculator
Shared module for consistent TP/SL calculation across screener and signal generator
"""

import pandas_ta as ta


def calculate_dynamic_tp_sl(df, current_price, signal_type='BUY'):
    """
    Calculate dynamic TP/SL based on technical levels
    
    Args:
        df: DataFrame with OHLCV + indicators (must have bb_upper, bb_lower)
        current_price: Current price
        signal_type: 'BUY' or 'SELL'
    
    Returns:
        dict with tp, sl, rr_ratio, tp_pct, sl_pct
    """
    try:
        # Get recent highs/lows (last 20 candles)
        recent_high = df['high'].tail(20).max()
        recent_low = df['low'].tail(20).min()
        
        # Bollinger Bands
        bb_upper = df['bb_upper'].iloc[-1] if 'bb_upper' in df.columns else current_price * 1.02
        bb_lower = df['bb_lower'].iloc[-1] if 'bb_lower' in df.columns else current_price * 0.98
        
        # ATR for volatility-based stops
        atr = ta.atr(df['high'], df['low'], df['close'], length=14).iloc[-1]
        
        if signal_type in ['BUY', 'STRONG_BUY']:
            # For BUY: TP must be ABOVE current price, SL must be BELOW
            # TP at resistance (recent high or BB upper)
            tp_candidates = [x for x in [recent_high, bb_upper] if x > current_price]
            if tp_candidates:
                tp = min(tp_candidates)  # Conservative (closest resistance)
            else:
                # No resistance above, use ATR
                tp = current_price + (atr * 2)
            
            # SL at support (recent low or BB lower)
            sl_candidates = [x for x in [recent_low, bb_lower] if x < current_price]
            if sl_candidates:
                sl = max(sl_candidates)  # Conservative (closest support)
            else:
                # No support below, use ATR
                sl = current_price - atr
            
            # Calculate R:R
            risk = current_price - sl
            reward = tp - current_price
            
            # Fallback if still invalid
            if risk <= 0 or reward <= 0:
                tp = current_price * 1.05  # 5% TP
                sl = current_price * 0.97  # 3% SL
                risk = current_price - sl
                reward = tp - current_price
            
            # Ensure minimum R:R of 1:1.5
            rr_ratio = reward / risk if risk > 0 else 1.0
            
            if rr_ratio < 1.5:
                # Adjust SL to achieve 1:1.5 R:R
                required_risk = reward / 1.5
                sl = current_price - required_risk
                # Don't let SL go below recent low - 2%
                min_sl = recent_low * 0.98
                if sl < min_sl:
                    # Instead, adjust TP
                    tp = current_price + (risk * 1.5)
                rr_ratio = 1.5
        
        else:  # SELL
            # For SELL: TP at support, SL at resistance
            tp = max(recent_low, bb_lower)
            sl = min(recent_high, bb_upper)
            
            risk = sl - current_price
            reward = current_price - tp
            
            if risk <= 0 or reward <= 0:
                tp = current_price - (atr * 1.5)
                sl = current_price + atr
                risk = sl - current_price
                reward = current_price - tp
            
            rr_ratio = reward / risk if risk > 0 else 1.0
            
            if rr_ratio < 1.5:
                required_risk = reward / 1.5
                sl = current_price + required_risk
                max_sl = recent_high * 1.02
                if sl > max_sl:
                    tp = current_price - (risk * 1.5)
                rr_ratio = 1.5
        
        # Calculate percentages
        tp_pct = ((tp - current_price) / current_price) * 100 if signal_type in ['BUY', 'STRONG_BUY'] else ((current_price - tp) / current_price) * 100
        sl_pct = ((current_price - sl) / current_price) * 100 if signal_type in ['BUY', 'STRONG_BUY'] else ((sl - current_price) / current_price) * 100
        
        return {
            'tp': round(tp, 4),
            'sl': round(sl, 4),
            'rr_ratio': round(rr_ratio, 2),
            'tp_pct': round(tp_pct, 2),
            'sl_pct': round(sl_pct, 2)
        }
        
    except Exception as e:
        print(f"Error calculating TP/SL: {e}")
        # Fallback to fixed percentages
        if signal_type in ['BUY', 'STRONG_BUY']:
            tp = current_price * 1.05
            sl = current_price * 0.95
        else:
            tp = current_price * 0.95
            sl = current_price * 1.05
        
        return {
            'tp': round(tp, 4),
            'sl': round(sl, 4),
            'rr_ratio': 1.0,
            'tp_pct': 5.0,
            'sl_pct': 5.0
        }
