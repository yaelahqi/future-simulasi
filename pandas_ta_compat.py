"""
pandas_ta compatibility wrapper for ta library.
Maps pandas_ta function calls to ta library classes.
"""

import ta as _ta


def rsi(close, length=14):
    """RSI wrapper"""
    return _ta.momentum.RSIIndicator(close, window=length).rsi()


def sma(close, length=20):
    """SMA wrapper"""
    return _ta.trend.SMAIndicator(close, window=length).sma_indicator()


def ema(close, length=20):
    """EMA wrapper"""
    return _ta.trend.EMAIndicator(close, window=length).ema_indicator()


def macd(close, fast=12, slow=26, signal=9):
    """MACD wrapper — returns dict like pandas_ta"""
    m = _ta.trend.MACD(
        close,
        window_slow=slow,
        window_fast=fast,
        window_sign=signal
    )
    return {
        'MACD_12_26_9': m.macd(),
        'MACDh_12_26_9': m.macd_diff(),
        'MACDs_12_26_9': m.macd_signal(),
    }


def bbands(close, length=20, std=2.0):
    """Bollinger Bands wrapper — returns dict like pandas_ta"""
    bb = _ta.volatility.BollingerBands(close, window=length, window_dev=std)
    return {
        'BBL_20_2.0': bb.bollinger_lband(),
        'BBM_20_2.0': bb.bollinger_mavg(),
        'BBU_20_2.0': bb.bollinger_hband(),
    }


def atr(high, low, close, length=14):
    """ATR wrapper"""
    return _ta.volatility.AverageTrueRange(
        high, low, close, window=length
    ).average_true_range()


def obv(close, volume):
    """On-Balance Volume wrapper"""
    return _ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()


def adx(high, low, close, length=14):
    """ADX wrapper"""
    return _ta.trend.ADXIndicator(high, low, close, window=length).adx()


def willr(high, low, close, length=14):
    """Williams %R wrapper"""
    return _ta.momentum.WilliamsRIndicator(high, low, close, lbp=length).williams_r()


def cci(high, low, close, length=20):
    """CCI wrapper"""
    return _ta.trend.CCIIndicator(high, low, close, window=length).cci()


def stoch(high, low, close, k=14, d=3):
    """Stochastic oscillator wrapper"""
    s = _ta.momentum.StochasticOscillator(high, low, close, window=k, smooth_window=d)
    return {
        'STOCHk_14_3_3': s.stoch(),
        'STOCHd_14_3_3': s.stoch_signal(),
    }


def mfi(high, low, close, volume, length=14):
    """Money Flow Index wrapper"""
    return _ta.volume.MFIIndicator(high, low, close, volume, window=length).money_flow_index()
