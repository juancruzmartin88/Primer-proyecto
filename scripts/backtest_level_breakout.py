"""Evalua la Ruptura de nivel estructural con volumen en BTC (29/09/2026).
Ver `src/strategies/level_breakout.py` para el diseño completo - a
diferencia de `volume_breakout.py` (rango de consolidacion), esta version
ancla la ruptura a un nivel estructural real (manual union fractal).

Piso de muestra fijado DESDE EL ARRANQUE (pedido explicito del usuario,
para no repetir el problema de `backtest_volume_breakout.py`, que no junto
ni la muestra minima de entrenamiento en ninguna de las 9 combinaciones
probadas): se necesitan al menos `MIN_TRAIN_SAMPLE` (8) trades en la 1ra
mitad para poder elegir umbral de volumen sin sobreajustar, y se marca
explicitamente si el total de señales crudas no llega a `MIN_IDEAL_SAMPLE`
(25) antes de reportar cualquier conclusion como definitiva.

Mismo protocolo de seleccion fuera de muestra que `backtest_regime_filter.py`
y `backtest_volume_breakout.py`: se barre el umbral de volumen SOLO sobre
la 1ra mitad cronologica de los trades del backtest exploratorio (lote
fijo), se elige la mejor de entrenamiento, y recien con eso fijo se corre
el backtest completo - la 2da mitad de esa corrida final es la validacion
fuera de muestra real.

Requiere volumen real (igual que `volume_breakout.py`) - usar el export de
MT5 con `<TICKVOL>` convertido a `time,open,high,low,close,volume`
(`data/btcusd_h1_volume.csv`), no el CSV de Twelve Data sin volumen.

Uso:
    python -m scripts.backtest_level_breakout data/btcusd_h1_volume.csv BTCUSD \
        --account-balance=707.24 --pip-size=0.01 --pip-value-per-lot=0.01
"""
from __future__ import annotations

import argparse

import pandas as pd
from loguru import logger

from src.backtester import BacktestResult, run_backtest
from src.config import RiskConfig
from src.risk_manager import RiskManager
from src.strategies.level_breakout import LevelBreakoutStrategy
from src.strategies.structural_pullback import StructuralPullbackStrategy
from src.types import Signal

CANDIDATE_VOLUME_MULTS = [1.3, 1.5, 2.0]
MIN_TRAIN_SAMPLE = 8
MIN_IDEAL_SAMPLE = 25


def load_csv(path: str, sep: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=sep)
    df.columns = [c.strip().lower() for c in df.columns]
    time_col = "time" if "time" in df.columns else "datetime"
    df = df.rename(columns={time_col: "time"})
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)
    keep = [c for c in ["time", "open", "high", "low", "close", "volume", "tick_volume", "real_volume"] if c in df.columns]
    return df[keep]


def raw_signals_by_time(strategy, data: pd.DataFrame, window_size: int = 260) -> dict:
    signals = {}
    for i in range(strategy.min_history, len(data)):
        window = data.iloc[max(0, i + 1 - window_size) : i + 1]
        signal = strategy.generate_signal(window)
        if signal in (Signal.BUY, Signal.SELL):
            signals[data["time"].iloc[i]] = signal
    return signals


def print_result(label: str, signals: int, result: BacktestResult) -> None:
    print(f"[{label}] señales={signals} | {result.summary()}")
    n = len(result.trades)
    half = n // 2
    if half >= 3:
        first = BacktestResult(trades=result.trades[:half], initial_balance=result.initial_balance)
        second = BacktestResult(trades=result.trades[half:], initial_balance=result.initial_balance)
        print(f"    1ra mitad: {first.summary()}")
        print(f"    2da mitad: {second.summary()}")
    else:
        print(f"    (muestra de {n} trades - muy chica para split de mitades confiable)")


def profit_factor(trades: list[dict]) -> float:
    gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def select_volume_mult(data: pd.DataFrame, symbol: str, levels_path: str) -> float | None:
    print(f"  {'Vol.mult':>9s} {'n total':>8s} {'n train':>8s} {'PF train':>9s}")
    best = None  # (pf_train, mult)
    for mult in CANDIDATE_VOLUME_MULTS:
        strategy = LevelBreakoutStrategy(
            symbol=symbol, timeframe="H1", levels_path=levels_path, volume_breakout_mult=mult
        )
        result = run_backtest(strategy, data, pip_size=0.01, pip_value_per_lot=0.01)
        trades = result.trades
        half = len(trades) // 2
        train = trades[:half]
        if len(train) < MIN_TRAIN_SAMPLE:
            print(f"  {mult:>9.1f} {len(trades):>8d} {len(train):>8d}      (muestra insuficiente)")
            continue
        pf_train = profit_factor(train)
        print(f"  {mult:>9.1f} {len(trades):>8d} {len(train):>8d} {pf_train:>9.2f}")
        if best is None or pf_train > best[0]:
            best = (pf_train, mult)

    if best is None:
        print("\n  Ninguna combinacion de umbral de volumen junto la muestra minima de entrenamiento.")
        return None

    pf_train, mult = best
    print(f"\n  Elegido: volumen>={mult}x (PF entrenamiento {pf_train:.2f})\n")
    return mult


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

    print("\n=== PASO 2: barrido de umbral de volumen, SOLO sobre entrenamiento ===\n")
    mult = select_volume_mult(data, args.symbol, args.levels_path)

    def make_strategy(m: float):
        return LevelBreakoutStrategy(symbol=args.symbol, timeframe="H1", levels_path=args.levels_path, volume_breakout_mult=m)

    # Con o sin umbral elegible, reportamos tambien el conteo crudo con el
    # umbral menos exigente (1.3x) para no dejar el diagnostico a ciegas si
    # el barrido no encontro muestra suficiente.
    probe_mult = mult if mult is not None else CANDIDATE_VOLUME_MULTS[0]
    probe_signals = raw_signals_by_time(make_strategy(probe_mult), data)
    print(f"Señales crudas con volumen>={probe_mult}x: {len(probe_signals)} (piso minimo ideal: {MIN_IDEAL_SAMPLE})")
    if len(probe_signals) < MIN_IDEAL_SAMPLE:
        print(
            f"ADVERTENCIA: por debajo del piso ideal de {MIN_IDEAL_SAMPLE} señales - "
            "cualquier conclusion de este backtest debe tratarse como preliminar, no como aprobacion/rechazo definitivo.\n"
        )
    if mult is None:
        return

    print(f"=== PASO 3: backtest completo con volumen>={mult}x ===\n")
    signals = raw_signals_by_time(make_strategy(mult), data)

    print("--- VISTA REALISTA (capital real, filtro seccion 3.2 activo) ---\n")
    result_real = run_backtest(
        make_strategy(mult), data, initial_balance=args.account_balance, pip_size=args.pip_size,
        pip_value_per_lot=args.pip_value_per_lot,
        risk_manager=RiskManager(RiskConfig(risk_per_trade_pct=args.risk_per_trade_pct, max_daily_loss_pct=100.0, max_open_positions=1)),
        is_real_account=True,
    )
    print_result("Ruptura de nivel con volumen", len(signals), result_real)

    print("\n--- VISTA EXPLORATORIA (lote fijo) ---\n")
    result_fixed = run_backtest(make_strategy(mult), data, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot)
    print_result("Ruptura de nivel con volumen (lote fijo)", len(signals), result_fixed)

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
