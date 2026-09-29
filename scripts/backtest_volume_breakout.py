"""Evalua la Ruptura estructural con volumen en BTC (30/09/2026) - diseño
nuevo tras agotar tendencia-pullback a EMA (3 intentos rechazados). Ver
`src/strategies/volume_breakout.py` para el diseño completo.

A diferencia del resto de los backtests de este proyecto sobre BTC (CSV de
Twelve Data, sin columna de volumen), este SI necesita volumen real - usa
el export de MT5 que el usuario subio (`data/btcusd_h1_volume.csv`,
convertido de `<DATE> <TIME> ... <TICKVOL>` a `time,open,high,low,close,volume`).

Seleccion de N (ventana de consolidacion) y umbral de volumen SIN
sobreajustar (pedido explicito del usuario, mismo protocolo que
`scripts/backtest_regime_filter.py`): se barre N x umbral SOLO sobre la
1ra mitad cronologica de los trades del benchmark exploratorio (lote
fijo), se elige la combinacion de mejor profit factor de entrenamiento, y
recien con eso fijo se corre el backtest completo - la 2da mitad de esa
corrida final es la validacion fuera de muestra real.

Uso:
    python -m scripts.backtest_volume_breakout data/btcusd_h1_volume.csv BTCUSD \
        --account-balance=707.24 --pip-size=0.01 --pip-value-per-lot=0.01
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from loguru import logger

from src.backtester import BacktestResult, run_backtest
from src.config import RiskConfig
from src.risk_manager import RiskManager
from src.strategies.structural_pullback import StructuralPullbackStrategy
from src.strategies.volume_breakout import VolumeBreakoutStrategy
from src.types import Signal

CANDIDATE_WINDOWS = [8, 10, 12]
CANDIDATE_VOLUME_MULTS = [1.3, 1.5, 2.0]
MIN_TRAIN_SAMPLE = 8


def load_csv(path: str, sep: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=sep)
    df.columns = [c.strip().lower() for c in df.columns]
    time_col = "time" if "time" in df.columns else "datetime"
    df = df.rename(columns={time_col: "time"})
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)
    keep = [c for c in ["time", "open", "high", "low", "close", "volume", "tick_volume", "real_volume"] if c in df.columns]
    return df[keep]


def count_raw_signals(strategy, data: pd.DataFrame, window_size: int = 200) -> int:
    count = 0
    for i in range(strategy.min_history, len(data)):
        window = data.iloc[max(0, i + 1 - window_size) : i + 1]
        if strategy.generate_signal(window) in (Signal.BUY, Signal.SELL):
            count += 1
    return count


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
        print(f"    1ra mitad (entrenamiento): {first.summary()}")
        print(f"    2da mitad (VALIDACION fuera de muestra): {second.summary()}")
    else:
        print(f"    (muestra de {len(result.trades)} trades - muy chica para split de mitades confiable)")


def profit_factor(trades: list[dict]) -> float:
    gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def select_params(data: pd.DataFrame, symbol: str, levels_path: str) -> tuple[int, float]:
    """Barre `CANDIDATE_WINDOWS` x `CANDIDATE_VOLUME_MULTS` corriendo el
    backtest exploratorio (lote fijo) COMPLETO por combinacion, pero
    evalua el profit factor solo sobre la 1ra mitad cronologica de los
    trades resultantes (entrenamiento) - la 2da mitad no influye en la
    eleccion, se usa recien despues como validacion.
    """
    print(f"  {'N':>4s} {'Vol.mult':>9s} {'n total':>8s} {'n train':>8s} {'PF train':>9s}")
    best = None  # (pf_train, window, mult)
    for window in CANDIDATE_WINDOWS:
        for mult in CANDIDATE_VOLUME_MULTS:
            strategy = VolumeBreakoutStrategy(
                symbol=symbol, timeframe="H1", levels_path=levels_path,
                consolidation_window=window, volume_breakout_mult=mult,
            )
            result = run_backtest(strategy, data, pip_size=0.01, pip_value_per_lot=0.01)
            trades = result.trades
            half = len(trades) // 2
            train = trades[:half]
            if len(train) < MIN_TRAIN_SAMPLE:
                print(f"  {window:>4d} {mult:>9.1f} {len(trades):>8d} {len(train):>8d}      (muestra insuficiente)")
                continue
            pf_train = profit_factor(train)
            print(f"  {window:>4d} {mult:>9.1f} {len(trades):>8d} {len(train):>8d} {pf_train:>9.2f}")
            if best is None or pf_train > best[0]:
                best = (pf_train, window, mult)

    if best is None:
        raise SystemExit("Ninguna combinacion N/umbral de volumen junto la muestra minima en entrenamiento.")

    pf_train, window, mult = best
    print(f"\n  Elegido: N={window}, volumen>={mult}x (PF entrenamiento {pf_train:.2f})\n")
    return window, mult


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("symbol")
    parser.add_argument("--sep", default=",")
    parser.add_argument("--levels-path", default="config/levels.json")
    parser.add_argument("--account-balance", type=float, default=707.24)
    parser.add_argument("--risk-per-trade-pct", type=float, default=2.0)
    parser.add_argument("--pip-size", type=float, default=0.01)
    parser.add_argument("--pip-value-per-lot", type=float, default=0.01)
    args = parser.parse_args()

    logger.remove()

    data = load_csv(args.csv_path, args.sep)
    has_volume = any(c in data.columns for c in ("volume", "tick_volume", "real_volume"))
    print(f"{args.symbol}: {len(data)} velas, {data['time'].iloc[0]} -> {data['time'].iloc[-1]} | volumen real: {has_volume}\n")
    if not has_volume:
        print("ADVERTENCIA: no hay columna de volumen - el filtro de volumen quedaria inerte, la seleccion de umbral no seria valida.\n")

    print("=== PASO 1: benchmark v2 (referencia) ===\n")
    v2 = StructuralPullbackStrategy(symbol=args.symbol, timeframe="H1", levels_path=args.levels_path)
    v2_signals = raw_signals_by_time(v2, data)
    v2_real = run_backtest(
        StructuralPullbackStrategy(symbol=args.symbol, timeframe="H1", levels_path=args.levels_path), data,
        initial_balance=args.account_balance, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot,
        risk_manager=RiskManager(RiskConfig(risk_per_trade_pct=args.risk_per_trade_pct, max_daily_loss_pct=100.0, max_open_positions=1)),
        is_real_account=True,
    )
    print_result("v2 (benchmark, realista)", len(v2_signals), v2_real)

    print("\n=== PASO 2: barrido de N x umbral de volumen, SOLO sobre entrenamiento ===\n")
    window, mult = select_params(data, args.symbol, args.levels_path)

    print(f"=== PASO 3: backtest completo (7 meses) con N={window}, volumen>={mult}x ===\n")

    def make_strategy():
        return VolumeBreakoutStrategy(
            symbol=args.symbol, timeframe="H1", levels_path=args.levels_path,
            consolidation_window=window, volume_breakout_mult=mult,
        )

    signals = raw_signals_by_time(make_strategy(), data)

    print("--- VISTA REALISTA (capital real, filtro seccion 3.2 activo) ---\n")
    result_real = run_backtest(
        make_strategy(), data, initial_balance=args.account_balance, pip_size=args.pip_size,
        pip_value_per_lot=args.pip_value_per_lot,
        risk_manager=RiskManager(RiskConfig(risk_per_trade_pct=args.risk_per_trade_pct, max_daily_loss_pct=100.0, max_open_positions=1)),
        is_real_account=True,
    )
    print_result("Ruptura estructural con volumen", len(signals), result_real)

    print("\n--- VISTA EXPLORATORIA (lote fijo) ---\n")
    result_fixed = run_backtest(make_strategy(), data, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot)
    print_result("Ruptura estructural con volumen (lote fijo)", len(signals), result_fixed)

    print("\n=== SOLAPAMIENTO/CONTRADICCION CON v2 ===\n")
    common_times = set(signals) & set(v2_signals)
    print(f"Velas con señal cruda de AMBAS a la vez: {len(common_times)} de {len(signals)} señales de ruptura")
    agreements = [t for t in common_times if signals[t] == v2_signals[t]]
    contradictions = [t for t in common_times if signals[t] != v2_signals[t]]
    print(f"  Misma dirección (redundante): {len(agreements)}")
    print(f"  DIRECCION CONTRADICTORIA: {len(contradictions)}")
    for t in sorted(contradictions)[:15]:
        print(f"    {t}: ruptura={signals[t].name} vs v2={v2_signals[t].name}")


if __name__ == "__main__":
    main()
