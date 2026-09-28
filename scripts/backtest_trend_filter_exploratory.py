"""Vista exploratoria (lote fijo, sin filtro de capital) del filtro de tendencia 4H.

Complementa scripts/backtest_trend_filter.py: en modo "realista" (con el
RiskManager bloqueando en cuenta real) las 3 variantes colapsan a 1 trade
ejecutable cada una (mismo cuello de botella de capital de siempre en
Oro) - no alcanza para juzgar si el filtro de tendencia mejora la CALIDAD
de la señal en sí. Esta vista aisla esa pregunta corriendo a lote fijo
1.0 (mismo patron que "Lote fijo 1.0" en scripts/backtest_from_csv.py).

Uso:
    python -m scripts.backtest_trend_filter_exploratory data/xauusd_h1_raw.csv XAUUSD --sep=";"
"""
from __future__ import annotations

import argparse

import pandas as pd
from loguru import logger

from src.backtester import BacktestResult, run_backtest
from src.strategies.structural_pullback import StructuralPullbackStrategy
from src.trend_filter import (
    TrendFilteredStrategy,
    map_trend_to_h1,
    resample_to_4h,
    trend_by_rsi,
    trend_by_sma,
    trend_by_structure,
)

VARIANTS = {
    "sma50_4h": lambda data_4h: trend_by_sma(data_4h, period=50),
    "rsi_4h": lambda data_4h: trend_by_rsi(data_4h, period=14),
    "estructura_4h": lambda data_4h: trend_by_structure(data_4h, lookback=20),
}


def load_csv(path: str, sep: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=sep)
    df.columns = [c.strip().lower() for c in df.columns]
    time_col = "time" if "time" in df.columns else "datetime"
    df = df.rename(columns={time_col: "time"})
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)
    return df[["time", "open", "high", "low", "close"]]


def print_result(label: str, result: BacktestResult) -> None:
    print(f"[{label}] {result.summary()}")
    half = len(result.trades) // 2
    if half >= 3:
        first = BacktestResult(trades=result.trades[:half], initial_balance=result.initial_balance)
        second = BacktestResult(trades=result.trades[half:], initial_balance=result.initial_balance)
        print(f"    1ra mitad: {first.summary()}")
        print(f"    2da mitad: {second.summary()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("symbol")
    parser.add_argument("--sep", default=",")
    parser.add_argument("--levels-path", default="config/levels.json")
    parser.add_argument("--pip-size", type=float, default=0.01)
    parser.add_argument("--pip-value-per-lot", type=float, default=1.0)
    args = parser.parse_args()

    logger.remove()

    data = load_csv(args.csv_path, args.sep)
    print(f"{args.symbol}: {len(data)} velas, {data['time'].iloc[0]} -> {data['time'].iloc[-1]}\n")

    data_4h = resample_to_4h(data)

    base = StructuralPullbackStrategy(symbol=args.symbol, timeframe="H1", levels_path=args.levels_path)
    baseline = run_backtest(base, data, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot)
    print_result("SIN filtro (benchmark actual, lote fijo)", baseline)
    print()

    for name, trend_fn in VARIANTS.items():
        trend_4h = trend_fn(data_4h)
        trend_h1 = map_trend_to_h1(data["time"], trend_4h)
        trend_by_time = dict(zip(data["time"], trend_h1))

        base_for_variant = StructuralPullbackStrategy(symbol=args.symbol, timeframe="H1", levels_path=args.levels_path)
        wrapped = TrendFilteredStrategy(base_for_variant, trend_by_time)

        result = run_backtest(wrapped, data, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot)
        print_result(f"CON filtro {name} (lote fijo)", result)
        print()


if __name__ == "__main__":
    main()
