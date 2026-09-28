"""Evalua el filtro de tendencia 4H sobre la Metodologia v2 en Oro (28/09/2026).

Compara el benchmark actual (sin filtro) contra 3 formas de definir la
tendencia mayor de 4H (ver src/trend_filter.py), descartando cualquier
señal de 1H que vaya en contra de esa tendencia. Reporta señales generadas,
trades ejecutados, win rate, profit factor y drawdown - modo realista
(bloqueo de riesgo como en cuenta real) y split de mitades para cada
variante, mismo estandar que el resto de las evaluaciones del proyecto.

Uso:
    python -m scripts.backtest_trend_filter data/xauusd_h1_raw.csv XAUUSD \
        --sep=";" --account-balance=715.24
"""
from __future__ import annotations

import argparse

import pandas as pd
from loguru import logger

from src.backtester import BacktestResult, run_backtest
from src.config import RiskConfig
from src.risk_manager import RiskManager
from src.strategies.structural_pullback import StructuralPullbackStrategy
from src.trend_filter import (
    TrendFilteredStrategy,
    map_trend_to_h1,
    resample_to_4h,
    trend_by_rsi,
    trend_by_sma,
    trend_by_structure,
)
from src.types import Signal

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


def count_raw_signals(strategy, data: pd.DataFrame, window_size: int = 200) -> int:
    count = 0
    for i in range(strategy.min_history, len(data)):
        window = data.iloc[max(0, i + 1 - window_size) : i + 1]
        if strategy.generate_signal(window) in (Signal.BUY, Signal.SELL):
            count += 1
    return count


def run_variant(strategy, data, *, account_balance, risk_pct, pip_size, pip_value_per_lot) -> BacktestResult:
    risk_manager = RiskManager(RiskConfig(risk_per_trade_pct=risk_pct, max_daily_loss_pct=100.0, max_open_positions=1))
    return run_backtest(
        strategy, data, initial_balance=account_balance, pip_size=pip_size, pip_value_per_lot=pip_value_per_lot,
        risk_manager=risk_manager, is_real_account=True,
    )


def print_result(label: str, signals: int, result: BacktestResult) -> None:
    print(f"[{label}] señales={signals} | {result.summary()}")
    half = len(result.trades) // 2
    if half >= 3:
        first = BacktestResult(trades=result.trades[:half], initial_balance=result.initial_balance)
        second = BacktestResult(trades=result.trades[half:], initial_balance=result.initial_balance)
        print(
            f"    1ra mitad: {first.summary()}\n"
            f"    2da mitad: {second.summary()}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("symbol")
    parser.add_argument("--sep", default=",")
    parser.add_argument("--levels-path", default="config/levels.json")
    parser.add_argument("--account-balance", type=float, default=715.24)
    parser.add_argument("--risk-per-trade-pct", type=float, default=2.0)
    parser.add_argument("--pip-size", type=float, default=0.01)
    parser.add_argument("--pip-value-per-lot", type=float, default=1.0)
    args = parser.parse_args()

    logger.remove()  # suprime el debug/warning de RiskManager - son miles de lineas en una corrida asi

    data = load_csv(args.csv_path, args.sep)
    print(f"{args.symbol}: {len(data)} velas, {data['time'].iloc[0]} -> {data['time'].iloc[-1]}\n")

    data_4h = resample_to_4h(data)

    base = StructuralPullbackStrategy(symbol=args.symbol, timeframe="H1", levels_path=args.levels_path)
    baseline_signals = count_raw_signals(base, data)
    baseline_result = run_variant(
        base, data, account_balance=args.account_balance, risk_pct=args.risk_per_trade_pct,
        pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot,
    )
    print_result("SIN filtro (benchmark actual)", baseline_signals, baseline_result)
    print()

    for name, trend_fn in VARIANTS.items():
        trend_4h = trend_fn(data_4h)
        trend_h1 = map_trend_to_h1(data["time"], trend_4h)
        trend_by_time = dict(zip(data["time"], trend_h1))

        base_for_variant = StructuralPullbackStrategy(symbol=args.symbol, timeframe="H1", levels_path=args.levels_path)
        wrapped = TrendFilteredStrategy(base_for_variant, trend_by_time)

        signals = count_raw_signals(wrapped, data)
        result = run_variant(
            wrapped, data, account_balance=args.account_balance, risk_pct=args.risk_per_trade_pct,
            pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot,
        )
        print_result(f"CON filtro {name}", signals, result)
        print()


if __name__ == "__main__":
    main()
