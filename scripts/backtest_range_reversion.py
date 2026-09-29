"""Evalua la Metodologia de rango en Oro (28/09/2026) - sistema SEPARADO de
la Metodologia v2, pensado para correr en PARALELO y cubrir el tiempo sin
señales de reversion (RSI sin llegar a 35/65). Ver
`src/strategies/range_reversion.py` para el diseño completo y las
decisiones de implementacion documentadas.

Corre el mismo doble reporte de siempre (realista con RiskManager,
exploratorio a lote fijo) con split de mitades, y ademas chequea
solapamiento/contradiccion de señales con la Metodologia v2 sobre la misma
serie - punto 4 pedido explicitamente por el usuario.

Uso:
    python -m scripts.backtest_range_reversion data/xauusd_h1_raw.csv XAUUSD \
        --sep=";" --account-balance=715.24
"""
from __future__ import annotations

import argparse

import pandas as pd
from loguru import logger

from src.backtester import BacktestResult, run_backtest
from src.config import RiskConfig
from src.risk_manager import RiskManager
from src.strategies.range_reversion import RangeReversionStrategy
from src.strategies.structural_pullback import StructuralPullbackStrategy
from src.types import Signal


def load_csv(path: str, sep: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=sep)
    df.columns = [c.strip().lower() for c in df.columns]
    time_col = "time" if "time" in df.columns else "datetime"
    df = df.rename(columns={time_col: "time"})
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)
    return df[["time", "open", "high", "low", "close"]]


def raw_signals_by_time(strategy, data: pd.DataFrame, window_size: int = 200) -> dict:
    signals = {}
    for i in range(strategy.min_history, len(data)):
        window = data.iloc[max(0, i + 1 - window_size) : i + 1]
        signal = strategy.generate_signal(window)
        if signal in (Signal.BUY, Signal.SELL):
            signals[data["time"].iloc[i]] = signal
    return signals


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
    parser.add_argument("--adx-threshold", type=float, default=20.0)
    parser.add_argument("--regime-confirmation-candles", type=int, default=8)
    parser.add_argument("--min-range-atr-mult", type=float, default=2.0)
    args = parser.parse_args()

    logger.remove()

    data = load_csv(args.csv_path, args.sep)
    print(f"{args.symbol}: {len(data)} velas, {data['time'].iloc[0]} -> {data['time'].iloc[-1]}\n")

    def make_range_strategy():
        return RangeReversionStrategy(
            symbol=args.symbol, timeframe="H1",
            adx_threshold=args.adx_threshold,
            regime_confirmation_candles=args.regime_confirmation_candles,
            min_range_atr_mult=args.min_range_atr_mult,
        )

    def make_v2_strategy():
        return StructuralPullbackStrategy(symbol=args.symbol, timeframe="H1", levels_path=args.levels_path)

    print("=== VISTA REALISTA (capital real, filtro seccion 3.2 activo) ===\n")

    range_signals = raw_signals_by_time(make_range_strategy(), data)
    risk_manager = RiskManager(
        RiskConfig(risk_per_trade_pct=args.risk_per_trade_pct, max_daily_loss_pct=100.0, max_open_positions=1)
    )
    range_result_real = run_backtest(
        make_range_strategy(), data, initial_balance=args.account_balance,
        pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot,
        risk_manager=risk_manager, is_real_account=True,
    )
    print_result("Rango (nuevo)", len(range_signals), range_result_real)
    print()

    print("\n=== VISTA EXPLORATORIA (lote fijo, aísla calidad de señal) ===\n")

    range_result_fixed = run_backtest(
        make_range_strategy(), data, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot
    )
    print_result("Rango (nuevo, lote fijo)", len(range_signals), range_result_fixed)
    print()

    print("\n=== BENCHMARK DE REFERENCIA: Metodologia v2 sobre el mismo período ===\n")

    v2_signals = raw_signals_by_time(make_v2_strategy(), data)
    risk_manager_v2 = RiskManager(
        RiskConfig(risk_per_trade_pct=args.risk_per_trade_pct, max_daily_loss_pct=100.0, max_open_positions=1)
    )
    v2_result_real = run_backtest(
        make_v2_strategy(), data, initial_balance=args.account_balance,
        pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot,
        risk_manager=risk_manager_v2, is_real_account=True,
    )
    print_result("v2 (benchmark, realista)", len(v2_signals), v2_result_real)
    v2_result_fixed = run_backtest(make_v2_strategy(), data, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot)
    print_result("v2 (benchmark, lote fijo)", len(v2_signals), v2_result_fixed)
    print()

    print("\n=== CHEQUEO DE SOLAPAMIENTO/CONTRADICCION CON v2 (punto 4) ===\n")
    common_times = set(range_signals) & set(v2_signals)
    print(f"Velas con señal cruda de AMBAS estrategias a la vez: {len(common_times)} de {len(range_signals)} señales de rango")
    contradictions = [t for t in common_times if range_signals[t] != v2_signals[t]]
    print(f"  De esas, con DIRECCION CONTRADICTORIA (una BUY, otra SELL): {len(contradictions)}")
    if contradictions:
        for t in sorted(contradictions)[:10]:
            print(f"    {t}: rango={range_signals[t].name} vs v2={v2_signals[t].name}")


if __name__ == "__main__":
    main()
