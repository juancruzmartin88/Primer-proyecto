"""Ventana de sincronizacion RSI-vela de rechazo en BTC (28/09/2026).

Surge del diagnostico de la sequia de 2 semanas en BTC: 33 casos con vela
de rechazo geometricamente valida desde el 16/09, ninguno coincidiendo con
un RSI genuinamente extremo en el mismo momento (29 sin toque reciente, 4
con toque pero sin haber girado de vuelta todavia). Prueba
`SyncWindowStrategy` (src/strategies/sync_window.py): en vez de exigir que
el RSI ya haya cruzado de vuelta el umbral para la vela de confirmacion,
exige que la vela de rechazo aparezca dentro de `sync_window` velas
despues del ultimo toque del extremo (2 y 3 velas, las dos variantes
pedidas) - todo lo demas de la Metodologia v2 queda igual.

Uso:
    python -m scripts.backtest_sync_window data/btcusd_h1_raw.csv BTCUSD \
        --sep=";" --account-balance=715.24 --pip-size=0.01 --pip-value-per-lot=0.01
"""
from __future__ import annotations

import argparse

import pandas as pd
from loguru import logger

from src.backtester import BacktestResult, run_backtest
from src.config import RiskConfig
from src.risk_manager import RiskManager
from src.strategies.structural_pullback import StructuralPullbackStrategy
from src.strategies.sync_window import SyncWindowStrategy
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
    parser.add_argument("--pip-value-per-lot", type=float, default=0.01)
    args = parser.parse_args()

    logger.remove()

    data = load_csv(args.csv_path, args.sep)
    print(f"{args.symbol}: {len(data)} velas, {data['time'].iloc[0]} -> {data['time'].iloc[-1]}\n")

    variants = {
        "Bot actual (benchmark)": lambda: StructuralPullbackStrategy(
            symbol=args.symbol, timeframe="H1", levels_path=args.levels_path
        ),
        "Ventana de sincronizacion = 2 velas": lambda: SyncWindowStrategy(
            symbol=args.symbol, timeframe="H1", levels_path=args.levels_path, sync_window=2
        ),
        "Ventana de sincronizacion = 3 velas": lambda: SyncWindowStrategy(
            symbol=args.symbol, timeframe="H1", levels_path=args.levels_path, sync_window=3
        ),
    }

    print("=== VISTA REALISTA (capital real, filtro seccion 3.2 activo) ===\n")

    for label, factory in variants.items():
        strategy = factory()
        signals = count_raw_signals(strategy, data)
        strategy_for_risk = factory()
        risk_manager = RiskManager(
            RiskConfig(risk_per_trade_pct=args.risk_per_trade_pct, max_daily_loss_pct=100.0, max_open_positions=1)
        )
        result = run_backtest(
            strategy_for_risk, data, initial_balance=args.account_balance,
            pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot,
            risk_manager=risk_manager, is_real_account=True,
        )
        print_result(label, signals, result)
        print()

    print("\n=== VISTA EXPLORATORIA (lote fijo, aísla calidad de señal) ===\n")

    for label, factory in variants.items():
        strategy = factory()
        result = run_backtest(strategy, data, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot)
        print_result(f"{label} (lote fijo)", len(result.trades), result)
        print()


if __name__ == "__main__":
    main()
