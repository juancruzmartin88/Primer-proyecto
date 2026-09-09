import pandas as pd

from src.candles import (
    is_bearish_engulfing,
    is_bullish_engulfing,
    is_doji,
    is_hammer,
    is_shooting_star,
)


def candle(open_, high, low, close):
    return pd.Series({"open": open_, "high": high, "low": low, "close": close})


def test_is_hammer_detects_long_lower_wick_small_body():
    c = candle(open_=101.0, high=101.05, low=99.9, close=100.9)
    assert is_hammer(c)
    assert not is_shooting_star(c)


def test_is_shooting_star_detects_long_upper_wick_small_body():
    c = candle(open_=199.5, high=200.5, low=199.45, close=199.55)
    assert is_shooting_star(c)
    assert not is_hammer(c)


def test_is_doji_detects_tiny_body():
    c = candle(open_=100.0, high=101.0, low=99.0, close=100.02)
    assert is_doji(c)


def test_is_doji_false_for_large_body():
    c = candle(open_=100.0, high=105.0, low=99.5, close=104.5)
    assert not is_doji(c)


def test_is_bullish_engulfing():
    prev = candle(open_=101.0, high=101.2, low=99.5, close=100.0)  # bajista
    curr = candle(open_=99.8, high=102.0, low=99.7, close=101.5)  # alcista, la engulle
    assert is_bullish_engulfing(prev, curr)
    assert not is_bearish_engulfing(prev, curr)


def test_is_bearish_engulfing():
    prev = candle(open_=100.0, high=101.2, low=99.8, close=101.0)  # alcista
    curr = candle(open_=101.2, high=101.3, low=99.0, close=99.5)  # bajista, la engulle
    assert is_bearish_engulfing(prev, curr)
    assert not is_bullish_engulfing(prev, curr)


def test_normal_candle_is_neither_hammer_nor_shooting_star():
    c = candle(open_=100.0, high=101.0, low=99.5, close=100.7)
    assert not is_hammer(c)
    assert not is_shooting_star(c)
