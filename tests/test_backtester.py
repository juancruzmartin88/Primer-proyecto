import numpy as np
import pandas as pd

from src.backtester import run_backtest
from src.strategies.sma_crossover import SmaCrossoverStrategy


def make_synthetic_trend_data(n: int = 300) -> pd.DataFrame:
    """Serie con tendencia alcista + ruido, suficiente para generar cruces de SMA."""
    rng = np.random.default_rng(seed=42)
    trend = np.linspace(1.1000, 1.1300, n)
    noise = rng.normal(0, 0.0015, n)
    close = trend + noise
    return pd.DataFrame(
        {
            "time": pd.date_range("2024-01-01", periods=n, freq="15min"),
            "open": close,
            "high": close + 0.0005,
            "low": close - 0.0005,
            "close": close,
        }
    )


def test_backtest_runs_and_produces_metrics():
    strategy = SmaCrossoverStrategy(symbol="EURUSD", timeframe="M15")
    data = make_synthetic_trend_data()

    result = run_backtest(strategy, data, initial_balance=10_000)

    # No afirmamos rentabilidad (séria data-snooping): solo que el motor
    # corre de punta a punta y produce metricas coherentes.
    assert isinstance(result.total_pnl, float)
    assert 0.0 <= result.win_rate <= 1.0
    assert 0.0 <= result.max_drawdown <= 1.0
    assert result.summary()  # no debe explotar al formatear
