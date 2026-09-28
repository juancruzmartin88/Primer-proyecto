import pandas as pd

from src.trend_filter import (
    TrendFilteredStrategy,
    map_trend_to_h1,
    resample_to_4h,
    trend_by_rsi,
    trend_by_sma,
    trend_by_structure,
)
from src.types import Signal


def _h1_candles(start, n, *, close_fn):
    times = pd.date_range(start, periods=n, freq="1h")
    closes = [close_fn(i) for i in range(n)]
    return pd.DataFrame(
        {
            "time": times,
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
        }
    )


def test_resample_to_4h_aggregates_ohlc_correctly():
    data = _h1_candles("2026-01-01 00:00", 8, close_fn=lambda i: 100 + i)
    data.loc[0, "high"] = 999  # el maximo del primer bloque de 4h
    data.loc[3, "low"] = -999  # el minimo del primer bloque de 4h

    result = resample_to_4h(data)

    assert len(result) == 2
    first = result.iloc[0]
    assert first["time"] == pd.Timestamp("2026-01-01 00:00")
    assert first["open"] == data.loc[0, "open"]
    assert first["high"] == 999
    assert first["low"] == -999
    assert first["close"] == data.loc[3, "close"]


def test_trend_by_sma_classifies_up_and_down():
    # precio subiendo por encima de un SMA50 que arranca chato en 100
    closes = [100.0] * 50 + [200.0] * 5
    data_4h = pd.DataFrame(
        {"time": pd.date_range("2026-01-01", periods=len(closes), freq="4h"), "close": closes,
         "open": closes, "high": closes, "low": closes}
    )

    trend = trend_by_sma(data_4h, period=50)

    assert trend.iloc[-1] == "up"


def test_trend_by_rsi_classifies_up_and_down():
    # racha alcista sostenida -> RSI > 50
    closes = [100.0 + i for i in range(30)]
    data_4h = pd.DataFrame(
        {"time": pd.date_range("2026-01-01", periods=len(closes), freq="4h"), "close": closes,
         "open": closes, "high": closes, "low": closes}
    )

    trend = trend_by_rsi(data_4h, period=14)

    assert trend.iloc[-1] == "up"

    closes_down = [200.0 - i for i in range(30)]
    data_4h_down = pd.DataFrame(
        {"time": pd.date_range("2026-01-01", periods=len(closes_down), freq="4h"), "close": closes_down,
         "open": closes_down, "high": closes_down, "low": closes_down}
    )
    assert trend_by_rsi(data_4h_down, period=14).iloc[-1] == "down"


def test_trend_by_structure_detects_higher_highs_and_higher_lows():
    # secuencia de fractales: HH+HL claros
    highs = [110, 100, 108, 100, 120, 100, 130]
    lows = [95, 90, 98, 85, 105, 95, 115]
    n = len(highs)
    data_4h = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=n, freq="4h"),
            "open": [(h + low) / 2 for h, low in zip(highs, lows)],
            "high": highs,
            "low": lows,
            "close": [(h + low) / 2 for h, low in zip(highs, lows)],
        }
    )

    trend = trend_by_structure(data_4h, lookback=n, fractal_window=1)

    assert trend.iloc[-1] == "up"


def test_trend_by_structure_detects_lower_highs_and_lower_lows():
    highs = [130, 120, 122, 100, 110, 90, 100]
    lows = [115, 105, 108, 85, 95, 75, 88]
    n = len(highs)
    data_4h = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=n, freq="4h"),
            "open": [(h + low) / 2 for h, low in zip(highs, lows)],
            "high": highs,
            "low": lows,
            "close": [(h + low) / 2 for h, low in zip(highs, lows)],
        }
    )

    trend = trend_by_structure(data_4h, lookback=n, fractal_window=1)

    assert trend.iloc[-1] == "down"


def test_map_trend_to_h1_has_no_lookahead():
    # Vela 4H "2026-01-01 00:00" (cubre 00:00-04:00) recien esta disponible
    # a partir de las 04:00 - un H1 a las 02:00 tiene que usar la vela 4H
    # ANTERIOR (la de las 20:00 del dia previo), no la que todavia esta
    # formandose.
    trend_4h = pd.Series(
        ["down", "up"],
        index=pd.to_datetime(["2025-12-31 20:00", "2026-01-01 00:00"]),
    )
    h1_times = pd.to_datetime(
        ["2026-01-01 01:00", "2026-01-01 02:00", "2026-01-01 03:00", "2026-01-01 04:00", "2026-01-01 05:00"]
    )

    mapped = map_trend_to_h1(pd.Series(h1_times), trend_4h)

    # 01-03hs: la vela 4h de las 00:00 todavia no cerro -> usa la anterior (down)
    assert list(mapped.iloc[:3]) == ["down", "down", "down"]
    # 04-05hs: la vela 4h de las 00:00 ya cerro -> usa "up"
    assert list(mapped.iloc[3:]) == ["up", "up"]


class _FakeBaseStrategy:
    symbol = "XAUUSDm"
    timeframe = "H1"
    min_history = 1

    def __init__(self, signal: Signal):
        self._signal = signal

    def generate_signal(self, data):
        return self._signal

    def stop_loss_price(self, data, signal):
        return 100.0

    def take_profit_price(self, data, signal):
        return 110.0


def _window(time):
    return pd.DataFrame({"time": [time], "open": [1], "high": [1], "low": [1], "close": [1]})


def test_trend_filtered_strategy_blocks_sell_in_uptrend():
    t = pd.Timestamp("2026-01-01 05:00")
    wrapped = TrendFilteredStrategy(_FakeBaseStrategy(Signal.SELL), {t: "up"})

    assert wrapped.generate_signal(_window(t)) == Signal.HOLD


def test_trend_filtered_strategy_blocks_buy_in_downtrend():
    t = pd.Timestamp("2026-01-01 05:00")
    wrapped = TrendFilteredStrategy(_FakeBaseStrategy(Signal.BUY), {t: "down"})

    assert wrapped.generate_signal(_window(t)) == Signal.HOLD


def test_trend_filtered_strategy_allows_aligned_signal():
    t = pd.Timestamp("2026-01-01 05:00")
    wrapped = TrendFilteredStrategy(_FakeBaseStrategy(Signal.BUY), {t: "up"})

    assert wrapped.generate_signal(_window(t)) == Signal.BUY


def test_trend_filtered_strategy_neutral_does_not_block():
    t = pd.Timestamp("2026-01-01 05:00")
    wrapped_buy = TrendFilteredStrategy(_FakeBaseStrategy(Signal.BUY), {t: "neutral"})
    wrapped_sell = TrendFilteredStrategy(_FakeBaseStrategy(Signal.SELL), {t: "neutral"})

    assert wrapped_buy.generate_signal(_window(t)) == Signal.BUY
    assert wrapped_sell.generate_signal(_window(t)) == Signal.SELL


def test_trend_filtered_strategy_delegates_sl_tp():
    t = pd.Timestamp("2026-01-01 05:00")
    wrapped = TrendFilteredStrategy(_FakeBaseStrategy(Signal.BUY), {t: "up"})

    assert wrapped.stop_loss_price(_window(t), Signal.BUY) == 100.0
    assert wrapped.take_profit_price(_window(t), Signal.BUY) == 110.0
