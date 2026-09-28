"""Evalua el filtro de piso de volatilidad (ATR) sobre la Metodologia v2 en Oro (28/09/2026).

Surge del diagnostico de la inconsistencia entre mitades: la 2da mitad del
periodo de referencia no fue mas volatil, fue mas lateral/comprimida, y
genero señales falsas adicionales sin sumar ganadoras. Prueba varios pisos
de ATR(14) sobre `src/volatility_filter.py`, con el mismo doble reporte
(realista con filtro de capital, exploratorio a lote fijo) y split de
mitades que el resto de las evaluaciones del proyecto.

Uso:
    python -m scripts.backtest_volatility_filter data/xauusd_h1_raw.csv XAUUSD \
        --sep=";" --account-balance=715.24 --atr-floors=14.27
"""
from __future__ import annotations

import argparse

import pandas as pd
from loguru import logger

from src.backtester import BacktestResult, run_backtest
from src.config import RiskConfig
from src.risk_manager import RiskManager
from src.strategies.structural_pullback import StructuralPullbackStrategy
from src.types import Signal
from src.volatility_filter import VolatilityFilteredStrategy


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


def print_result(label: str, signals: int, result: BacktestResult) -> None:
    print(f"[{label}] señales={signals} | {result.summary()}")
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
    parser.add_argument("--account-balance", type=float, default=715.24)
    parser.add_argument("--risk-per-trade-pct", type=float, default=2.0)
    parser.add_argument("--pip-size", type=float, default=0.01)
    parser.add_argument("--pip-value-per-lot", type=float, default=1.0)
    parser.add_argument("--atr-floors", type=str, default="14.27", help="Lista de pisos de ATR separados por coma.")
    args = parser.parse_args()

    logger.remove()

    floors = [float(x) for x in args.atr_floors.split(",")]
    data = load_csv(args.csv_path, args.sep)
    print(f"{args.symbol}: {len(data)} velas, {data['time'].iloc[0]} -> {data['time'].iloc[-1]}\n")

    print("=== VISTA REALISTA (capital real, filtro seccion 3.2 activo) ===\n")

    base = StructuralPullbackStrategy(symbol=args.symbol, timeframe="H1", levels_path=args.levels_path)
    baseline_signals = count_raw_signals(base, data)
    risk_manager = RiskManager(RiskConfig(risk_per_trade_pct=args.risk_per_trade_pct, max_daily_loss_pct=100.0, max_open_positions=1))
    baseline_result = run_backtest(
        base, data, initial_balance=args.account_balance, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot,
        risk_manager=risk_manager, is_real_account=True,
    )
    print_result("SIN filtro (benchmark actual)", baseline_signals, baseline_result)
    print()

    for floor in floors:
        base_for_variant = StructuralPullbackStrategy(symbol=args.symbol, timeframe="H1", levels_path=args.levels_path)
        wrapped = VolatilityFilteredStrategy(base_for_variant, atr_floor=floor)
        signals = count_raw_signals(wrapped, data)
        risk_manager = RiskManager(RiskConfig(risk_per_trade_pct=args.risk_per_trade_pct, max_daily_loss_pct=100.0, max_open_positions=1))
        result = run_backtest(
            wrapped, data, initial_balance=args.account_balance, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot,
            risk_manager=risk_manager, is_real_account=True,
        )
        print_result(f"CON piso ATR>={floor:.2f}", signals, result)
        print()

    print("\n=== VISTA EXPLORATORIA (lote fijo, aisla calidad de señal) ===\n")

    base = StructuralPullbackStrategy(symbol=args.symbol, timeframe="H1", levels_path=args.levels_path)
    baseline_result = run_backtest(base, data, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot)
    print_result("SIN filtro (benchmark actual, lote fijo)", len(baseline_result.trades), baseline_result)
    print()

    for floor in floors:
        base_for_variant = StructuralPullbackStrategy(symbol=args.symbol, timeframe="H1", levels_path=args.levels_path)
        wrapped = VolatilityFilteredStrategy(base_for_variant, atr_floor=floor)
        result = run_backtest(wrapped, data, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot)
        print_result(f"CON piso ATR>={floor:.2f} (lote fijo)", len(result.trades), result)
        print()


if __name__ == "__main__":
    main()
