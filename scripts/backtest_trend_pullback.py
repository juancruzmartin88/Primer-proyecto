"""Evalua la variante de tendencia con pullback a EMA en Oro (28-29/09/2026)
- sistema SEPARADO de la Metodologia v2 (reversion), esta es de SEGUIMIENTO
de tendencia. Ver `src/strategies/trend_pullback.py` para el diseño
completo. Corre el mismo doble reporte de siempre (realista con
RiskManager, exploratorio a lote fijo) con split de mitades, mas el
chequeo de solapamiento/contradiccion con v2 sobre la misma serie - acá
es mas probable que haya cruce que con la estrategia de rango, porque las
dos usan la misma vela de rechazo geometrica.

El benchmark de v2 se calcula una sola vez (no por variante), mismo
patron de `backtest_range_reversion.py`.

Uso:
    python -m scripts.backtest_trend_pullback data/xauusd_h1_raw.csv XAUUSD \
        --sep=";" --account-balance=707.24
"""
from __future__ import annotations

import argparse

import pandas as pd
from loguru import logger

from src.backtester import BacktestResult, run_backtest
from src.config import RiskConfig
from src.risk_manager import RiskManager
from src.strategies.structural_pullback import StructuralPullbackStrategy
from src.strategies.trend_pullback import TrendPullbackStrategy
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
    parser.add_argument("--account-balance", type=float, default=707.24)
    parser.add_argument("--risk-per-trade-pct", type=float, default=2.0)
    parser.add_argument("--pip-size", type=float, default=0.01)
    parser.add_argument("--pip-value-per-lot", type=float, default=1.0)
    args = parser.parse_args()

    logger.remove()

    data = load_csv(args.csv_path, args.sep)
    print(f"{args.symbol}: {len(data)} velas, {data['time'].iloc[0]} -> {data['time'].iloc[-1]}\n")

    def make_trend_strategy():
        return TrendPullbackStrategy(symbol=args.symbol, timeframe="H1", levels_path=args.levels_path)

    def make_v2_strategy():
        return StructuralPullbackStrategy(symbol=args.symbol, timeframe="H1", levels_path=args.levels_path)

    print("=== BENCHMARK DE REFERENCIA: Metodologia v2 (una sola vez) ===\n")
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

    print("\n\n########## TENDENCIA CON PULLBACK A EMA ##########\n")

    trend_signals = raw_signals_by_time(make_trend_strategy(), data)

    print("=== VISTA REALISTA (capital real, filtro seccion 3.2 activo) ===\n")
    risk_manager = RiskManager(
        RiskConfig(risk_per_trade_pct=args.risk_per_trade_pct, max_daily_loss_pct=100.0, max_open_positions=1)
    )
    trend_result_real = run_backtest(
        make_trend_strategy(), data, initial_balance=args.account_balance,
        pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot,
        risk_manager=risk_manager, is_real_account=True,
    )
    print_result("Tendencia-pullback", len(trend_signals), trend_result_real)

    print("\n=== VISTA EXPLORATORIA (lote fijo) ===\n")
    trend_result_fixed = run_backtest(
        make_trend_strategy(), data, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot
    )
    print_result("Tendencia-pullback (lote fijo)", len(trend_signals), trend_result_fixed)

    print("\n=== SOLAPAMIENTO/CONTRADICCION CON v2 ===\n")
    common_times = set(trend_signals) & set(v2_signals)
    print(f"Velas con señal cruda de AMBAS a la vez: {len(common_times)} de {len(trend_signals)} señales de tendencia-pullback")
    agreements = [t for t in common_times if trend_signals[t] == v2_signals[t]]
    contradictions = [t for t in common_times if trend_signals[t] != v2_signals[t]]
    print(f"  Misma dirección (redundante): {len(agreements)}")
    print(f"  DIRECCION CONTRADICTORIA: {len(contradictions)}")
    for t in sorted(contradictions)[:15]:
        print(f"    {t}: tendencia={trend_signals[t].name} vs v2={v2_signals[t].name}")


if __name__ == "__main__":
    main()
