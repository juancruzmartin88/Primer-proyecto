import numpy as np
import pandas as pd
import pytest

from src.indicators import adx, atr, ema, efficiency_ratio, rsi


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


def test_adx_is_high_for_a_strong_sustained_trend():
    n = 60
    trend = np.arange(100, 100 + n, dtype=float)
    data = pd.DataFrame({"high": trend + 1.0, "low": trend - 0.5, "close": trend + 0.5})
    result = adx(data, period=14)
    assert result.iloc[-1] > 60.0


def test_adx_is_low_for_a_ranging_market():
    n = 60
    np.random.seed(7)
    center = 100 + 1.5 * np.sin(np.cumsum(np.random.normal(0, 0.15, n)))
    data = pd.DataFrame(
        {
            "high": center + np.abs(np.random.normal(0.1, 0.05, n)),
            "low": center - np.abs(np.random.normal(0.1, 0.05, n)),
            "close": center,
        }
    )
    result = adx(data, period=14)
    assert result.iloc[-1] < 30.0


def test_adx_trend_exceeds_range_on_the_same_period():
    # Comparacion directa, mas robusta que umbrales absolutos: una
    # tendencia sostenida siempre tiene que dar un ADX mayor que un rango,
    # sea cual sea el umbral exacto que se termine usando en produccion.
    n = 40
    trend = np.arange(100, 100 + n, dtype=float)
    trending = pd.DataFrame({"high": trend + 1.0, "low": trend - 0.5, "close": trend + 0.5})

    flat = pd.Series([101.0, 100.8, 101.2, 100.9, 101.1] * (n // 5))
    ranging = pd.DataFrame({"high": flat + 0.15, "low": flat - 0.15, "close": flat})

    assert adx(trending, period=14).iloc[-1] > adx(ranging, period=14).iloc[-1]


def test_ema_converges_to_a_new_constant_level():
    closes = pd.Series([100.0] * 20 + [110.0] * 20)
    result = ema(closes, period=10)
    assert result.iloc[-1] == pytest.approx(110.0, abs=0.5)


def test_ema_reacts_faster_than_sma_of_the_same_period():
    from src.indicators import sma

    closes = pd.Series([100.0] * 20 + [110.0] * 5)
    ema_value = ema(closes, period=10).iloc[-1]
    sma_value = sma(closes, period=10).iloc[-1]
    assert ema_value > sma_value


def test_efficiency_ratio_is_close_to_1_for_a_straight_trend():
    closes = pd.Series([100 + i * 0.5 for i in range(30)])
    result = efficiency_ratio(closes, period=14)
    assert result.iloc[-1] == pytest.approx(1.0, abs=0.01)


def test_efficiency_ratio_is_close_to_0_for_pure_noise_around_a_level():
    np.random.seed(3)
    closes = pd.Series(100 + np.random.normal(0, 1, 30))
    result = efficiency_ratio(closes, period=14)
    assert result.iloc[-1] < 0.3


def test_efficiency_ratio_exceeds_noise_on_the_same_period_when_trending():
    n = 30
    trend = pd.Series([100 + i * 0.5 for i in range(n)])
    np.random.seed(3)
    noise = pd.Series(100 + np.random.normal(0, 1, n))
    assert efficiency_ratio(trend, period=14).iloc[-1] > efficiency_ratio(noise, period=14).iloc[-1]


def test_efficiency_ratio_is_zero_when_price_is_perfectly_flat():
    closes = pd.Series([100.0] * 30)
    result = efficiency_ratio(closes, period=14)
    assert result.iloc[-1] == 0.0
