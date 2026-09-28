import pandas as pd

from src.types import Signal
from src.volatility_filter import VolatilityFilteredStrategy


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


def _flat_low_volatility_window(n: int = 20) -> pd.DataFrame:
    # rango casi nulo vela a vela -> ATR bajo
    times = pd.date_range("2026-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"time": times, "open": [100.0] * n, "high": [100.1] * n, "low": [99.9] * n, "close": [100.0] * n}
    )


def _volatile_window(n: int = 20) -> pd.DataFrame:
    # rango grande vela a vela -> ATR alto
    times = pd.date_range("2026-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"time": times, "open": [100.0] * n, "high": [130.0] * n, "low": [70.0] * n, "close": [100.0] * n}
    )


def test_blocks_signal_when_atr_below_floor():
    wrapped = VolatilityFilteredStrategy(_FakeBaseStrategy(Signal.BUY), atr_floor=10.0)

    assert wrapped.generate_signal(_flat_low_volatility_window()) == Signal.HOLD


def test_allows_signal_when_atr_at_or_above_floor():
    wrapped = VolatilityFilteredStrategy(_FakeBaseStrategy(Signal.BUY), atr_floor=10.0)

    assert wrapped.generate_signal(_volatile_window()) == Signal.BUY


def test_hold_from_base_strategy_passes_through_without_computing_atr():
    wrapped = VolatilityFilteredStrategy(_FakeBaseStrategy(Signal.HOLD), atr_floor=10.0)

    assert wrapped.generate_signal(_flat_low_volatility_window()) == Signal.HOLD


def test_delegates_sl_tp_to_base():
    wrapped = VolatilityFilteredStrategy(_FakeBaseStrategy(Signal.SELL), atr_floor=1.0)
    window = _volatile_window()

    assert wrapped.stop_loss_price(window, Signal.SELL) == 100.0
    assert wrapped.take_profit_price(window, Signal.SELL) == 110.0


def test_exposes_symbol_timeframe_and_min_history_from_base():
    base = _FakeBaseStrategy(Signal.BUY)
    wrapped = VolatilityFilteredStrategy(base, atr_floor=5.0)

    assert wrapped.symbol == base.symbol
    assert wrapped.timeframe == base.timeframe
    assert wrapped.min_history == base.min_history
