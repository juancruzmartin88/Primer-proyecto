"""Metodologia v2 en Oro, timeframe 4H en vez de 1H (28/09/2026) - primer paso
para evaluar sumar swing trading al day trading actual.

Mismo esqueleto ya validado y en produccion (RSI 35/65, vela de rechazo con
el mismo test geometrico estricto, nivel estructural, SL por estructura +
margen de ATR, TP al proximo nivel) - `StructuralPullbackStrategy` no se
toca, solo cambia `timeframe="H4"` y los datos de entrada. Las velas 4H se
arman resampleando el mismo CSV H1 de referencia (7 meses, Twelve Data) con
`resample_to_4h` (src/trend_filter.py, ya usada y testeada para el filtro
de tendencia 4H) - mismo periodo, sin descargar datos nuevos.

Reporta desde el arranque las dos vistas (exploratoria y realista con el
filtro de capital seccion 3.2) para no descubrir tarde si el SL en 4H
(esperablemente mas ancho que en 1H) vuela el filtro de capital, igual que
paso con el piso de volatilidad.

Uso:
    python -m scripts.backtest_gold_4h data/xauusd_h1_raw.csv XAUUSD --sep=";"
"""
from __future__ import annotations

import argparse

import pandas as pd
from loguru import logger

from src.backtester import BacktestResult, run_backtest
from src.config import RiskConfig
from src.risk_manager import RiskManager
from src.strategies.structural_pullback import StructuralPullbackStrategy
from src.trend_filter import resample_to_4h
from src.types import Signal


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
    else:
        print(f"    (muestra de {len(result.trades)} trades - muy chica para split de mitades confiable)")


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

    logger.remove()

    data_h1 = load_csv(args.csv_path, args.sep)
    data_4h = resample_to_4h(data_h1)
    print(
        f"{args.symbol} 1H: {len(data_h1)} velas, {data_h1['time'].iloc[0]} -> {data_h1['time'].iloc[-1]}"
    )
    print(
        f"{args.symbol} 4H (resampleado): {len(data_4h)} velas, "
        f"{data_4h['time'].iloc[0]} -> {data_4h['time'].iloc[-1]}\n"
    )

    print("=== VISTA EXPLORATORIA (lote fijo, aísla calidad de señal) ===\n")

    strategy = StructuralPullbackStrategy(symbol=args.symbol, timeframe="H4", levels_path=args.levels_path)
    signals_exploratory = count_raw_signals(strategy, data_4h)
    strategy_for_fixed = StructuralPullbackStrategy(symbol=args.symbol, timeframe="H4", levels_path=args.levels_path)
    fixed_lot_result = run_backtest(
        strategy_for_fixed, data_4h, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot
    )
    print_result("Oro 4H (lote fijo)", signals_exploratory, fixed_lot_result)
    print()

    print("=== VISTA REALISTA (capital real, filtro seccion 3.2 activo) ===\n")

    strategy_for_risk = StructuralPullbackStrategy(symbol=args.symbol, timeframe="H4", levels_path=args.levels_path)
    risk_manager = RiskManager(
        RiskConfig(risk_per_trade_pct=args.risk_per_trade_pct, max_daily_loss_pct=100.0, max_open_positions=1)
    )
    risk_based_result = run_backtest(
        strategy_for_risk, data_4h, initial_balance=args.account_balance,
        pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot,
        risk_manager=risk_manager, is_real_account=True,
    )
    print_result(
        f"Oro 4H (riesgo {args.risk_per_trade_pct:.1f}% sobre ${args.account_balance:.2f}, real)",
        signals_exploratory,
        risk_based_result,
    )


if __name__ == "__main__":
    main()
