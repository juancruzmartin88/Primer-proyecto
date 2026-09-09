import pandas as pd
import pytest

from src.indicators import atr, rsi


def test_rsi_is_100_after_only_gains():
    closes = pd.Series([100, 101, 102, 103, 104, 105, 106, 107])
    result = rsi(closes, period=3)
    assert result.iloc[-1] == pytest.approx(100.0)


def test_rsi_is_0_after_only_losses():
    closes = pd.Series([107, 106, 105, 104, 103, 102, 101, 100])
    result = rsi(closes, period=3)
    assert result.iloc[-1] == pytest.approx(0.0)


def test_rsi_is_mid_range_for_alternating_moves_of_equal_size():
    # Con ganancias y perdidas de igual magnitud alternadas, el RSI no
    # debe irse a los extremos (0 o 100): tiene que quedar en zona neutral.
    closes = pd.Series([100, 101, 100, 101, 100, 101, 100, 101])
    result = rsi(closes, period=3)
    assert 30.0 < result.iloc[-1] < 70.0


def test_atr_is_positive_for_volatile_data():
    data = pd.DataFrame(
        {
            "high": [101, 103, 102, 105, 104],
            "low": [99, 100, 99, 101, 100],
            "close": [100, 102, 100, 104, 102],
        }
    )
    result = atr(data, period=3)
    assert result.iloc[-1] > 0


def test_atr_matches_constant_true_range():
    # Si el rango de cada vela es siempre el mismo y no hay gaps, el ATR
    # converge a ese rango.
    data = pd.DataFrame(
        {
            "high": [102.0] * 10,
            "low": [100.0] * 10,
            "close": [101.0] * 10,
        }
    )
    result = atr(data, period=3)
    assert result.iloc[-1] == pytest.approx(2.0, abs=0.01)
