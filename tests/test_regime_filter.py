import numpy as np
import pandas as pd

from src.regime_filter import RegimeFilteredStrategy
from src.types import Signal


class _FakeBaseStrategy:
    symbol = "BTCUSDm"
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


def _strong_trend_window(n: int = 20) -> pd.DataFrame:
    # Tendencia recta -> Efficiency Ratio cercano a 1 (regimen de tendencia fuerte).
    times = pd.date_range("2026-01-01", periods=n, freq="1h")
    closes = [100 + i * 0.5 for i in range(n)]
    return pd.DataFrame(
        {"time": times, "open": closes, "high": [c + 0.1 for c in closes], "low": [c - 0.1 for c in closes], "close": closes}
    )


def _choppy_window(n: int = 20) -> pd.DataFrame:
    # Oscilacion sin direccion neta -> Efficiency Ratio cercano a 0.
    np.random.seed(1)
    times = pd.date_range("2026-01-01", periods=n, freq="1h")
    closes = list(100 + np.random.normal(0, 1, n))
    return pd.DataFrame(
        {"time": times, "open": closes, "high": [c + 0.2 for c in closes], "low": [c - 0.2 for c in closes], "close": closes}
    )


def test_blocks_signal_when_er_above_ceiling():
    wrapped = RegimeFilteredStrategy(_FakeBaseStrategy(Signal.BUY), er_ceiling=0.3, er_period=14)

    assert wrapped.generate_signal(_strong_trend_window()) == Signal.HOLD


def test_allows_signal_when_er_at_or_below_ceiling():
    wrapped = RegimeFilteredStrategy(_FakeBaseStrategy(Signal.BUY), er_ceiling=0.3, er_period=14)

    assert wrapped.generate_signal(_choppy_window()) == Signal.BUY


def test_hold_from_base_strategy_passes_through_without_computing_er():
    wrapped = RegimeFilteredStrategy(_FakeBaseStrategy(Signal.HOLD), er_ceiling=0.3, er_period=14)

    assert wrapped.generate_signal(_strong_trend_window()) == Signal.HOLD


def test_delegates_sl_tp_to_base():
    wrapped = RegimeFilteredStrategy(_FakeBaseStrategy(Signal.SELL), er_ceiling=1.0, er_period=14)
    window = _choppy_window()

    assert wrapped.stop_loss_price(window, Signal.SELL) == 100.0
    assert wrapped.take_profit_price(window, Signal.SELL) == 110.0


def test_exposes_symbol_timeframe_and_min_history_from_base():
    base = _FakeBaseStrategy(Signal.BUY)
    wrapped = RegimeFilteredStrategy(base, er_ceiling=0.5, er_period=14)

    assert wrapped.symbol == base.symbol
    assert wrapped.timeframe == base.timeframe
    assert wrapped.min_history == base.min_history
