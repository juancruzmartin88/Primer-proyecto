"""Evalua un filtro de regimen dinamico (techo de Efficiency Ratio de
Kaufman) sobre la Metodologia v2 en BTC (30/09/2026). Hipotesis del
usuario: v2 es una estrategia de REVERSION, asi que podria rendir peor
cuando el mercado esta en tendencia fuerte sostenida (entra contra un
movimiento que sigue de largo en vez de revertir) - descartar la señal si
el ER(periodo) en ese momento supera un techo, quedandose afuera de los
regimenes de tendencia mas marcada.

Selección de umbral SIN mirar el periodo completo, para evitar
sobreajuste (pedido explicito del usuario): se usa la 1ra mitad
cronologica de los trades del benchmark exploratorio (lote fijo, aisla
calidad de señal) como "entrenamiento" - ahi se prueban varios periodos de
ER y varios percentiles de umbral, y se elige la combinacion con mejor
profit factor DENTRO de esa mitad solamente (con un piso minimo de
muestra). Recien con esa combinacion ya fija se corre el backtest
completo (las dos vistas de siempre) sobre los 7 meses enteros - la 2da
mitad de esa corrida es la validacion fuera de muestra real: si el filtro
solo funciona en la mitad donde se eligio el umbral y se cae en la otra,
es sobreajuste, no una mejora genuina.

Uso:
    python -m scripts.backtest_regime_filter data/btcusd_h1_raw.csv BTCUSD \
        --sep=";" --account-balance=707.24 --pip-size=0.01 --pip-value-per-lot=0.01
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from loguru import logger

from src.backtester import BacktestResult, run_backtest
from src.config import RiskConfig
from src.indicators import efficiency_ratio
from src.regime_filter import RegimeFilteredStrategy
from src.risk_manager import RiskManager
from src.strategies.structural_pullback import StructuralPullbackStrategy
from src.types import Signal

CANDIDATE_PERIODS = [14, 17, 20]
CANDIDATE_QUANTILES = [0.5, 0.6, 0.7, 0.8]
MIN_TRAIN_SAMPLE = 8


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


def select_threshold(train_trades: list[dict], er_by_period: dict[int, pd.Series], time_to_idx: dict) -> tuple[int, float]:
    """Barre periodo x percentil SOLO sobre `train_trades`, sin tocar la
    mitad de validacion. Devuelve (periodo, umbral de ER) de la combinacion
    con mejor profit factor de entrenamiento que respete `MIN_TRAIN_SAMPLE`.
    """
    baseline_pf = profit_factor(train_trades)
    print(f"  Benchmark sin filtro (entrenamiento, n={len(train_trades)}): PF={baseline_pf:.2f}\n")

    best = None  # (pf, period, threshold, n_kept)
    print(f"  {'Periodo':>8s} {'Percentil':>10s} {'Umbral ER':>10s} {'n kept':>7s} {'PF train':>9s}")
    for period in CANDIDATE_PERIODS:
        er_series = er_by_period[period]
        er_values = []
        for t in train_trades:
            idx = time_to_idx.get(t["entry_time"])
            er_values.append(er_series.iloc[idx] if idx is not None else np.nan)
        for i, t in enumerate(train_trades):
            t[f"er_{period}"] = er_values[i]

        valid_er = [v for v in er_values if not pd.isna(v)]
        if not valid_er:
            continue
        for q in CANDIDATE_QUANTILES:
            threshold = float(np.quantile(valid_er, q))
            kept = [t for t, er in zip(train_trades, er_values) if not pd.isna(er) and er <= threshold]
            if len(kept) < MIN_TRAIN_SAMPLE:
                print(f"  {period:>8d} {q:>10.2f} {threshold:>10.4f} {len(kept):>7d}      (muestra insuficiente)")
                continue
            pf = profit_factor(kept)
            print(f"  {period:>8d} {q:>10.2f} {threshold:>10.4f} {len(kept):>7d} {pf:>9.2f}")
            if best is None or pf > best[0]:
                best = (pf, period, threshold, len(kept))

    if best is None:
        raise SystemExit("Ninguna combinacion periodo/percentil junto la muestra minima en entrenamiento.")

    pf, period, threshold, n_kept = best
    print(
        f"\n  Elegido: ER({period}) <= {threshold:.4f} "
        f"(PF entrenamiento {pf:.2f} sobre {n_kept} trades, vs benchmark sin filtro {baseline_pf:.2f})\n"
    )
    return period, threshold


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
    print(f"{args.symbol}: {len(data)} velas, {data['time'].iloc[0]} -> {data['time'].iloc[-1]}\n")

    def make_base():
        return StructuralPullbackStrategy(symbol=args.symbol, timeframe="H1", levels_path=args.levels_path)

    print("=== PASO 1: benchmark v2 exploratorio (lote fijo), aisla calidad de señal ===\n")
    baseline_result = run_backtest(make_base(), data, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot)
    print(f"Benchmark completo: {baseline_result.summary()}\n")

    time_to_idx = {t: i for i, t in enumerate(data["time"])}
    er_by_period = {p: efficiency_ratio(data["close"], period=p) for p in CANDIDATE_PERIODS}

    half = len(baseline_result.trades) // 2
    train_trades = [dict(t) for t in baseline_result.trades[:half]]
    test_trades_count = len(baseline_result.trades) - half
    print(
        f"Split para seleccion de umbral: {half} trades de entrenamiento (1ra mitad cronologica), "
        f"{test_trades_count} quedan de validacion (2da mitad, NO se usan para elegir el umbral)\n"
    )

    print("=== PASO 2: barrido de periodo x percentil de ER, SOLO sobre entrenamiento ===\n")
    period, threshold = select_threshold(train_trades, er_by_period, time_to_idx)

    print(f"=== PASO 3: backtest completo (7 meses) con ER({period})<={threshold:.4f} ===\n")

    def make_filtered():
        return RegimeFilteredStrategy(make_base(), er_ceiling=threshold, er_period=period)

    print("--- Benchmark v2 SIN filtro (referencia, recalculado) ---\n")
    signals_baseline = count_raw_signals(make_base(), data)
    v2_real = run_backtest(
        make_base(), data, initial_balance=args.account_balance, pip_size=args.pip_size,
        pip_value_per_lot=args.pip_value_per_lot,
        risk_manager=RiskManager(RiskConfig(risk_per_trade_pct=args.risk_per_trade_pct, max_daily_loss_pct=100.0, max_open_positions=1)),
        is_real_account=True,
    )
    print_result("v2 sin filtro (realista)", signals_baseline, v2_real)
    v2_fixed = run_backtest(make_base(), data, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot)
    print_result("v2 sin filtro (lote fijo)", len(v2_fixed.trades), v2_fixed)

    print("\n--- CON filtro de regimen ---\n")
    signals_filtered = count_raw_signals(make_filtered(), data)
    filtered_real = run_backtest(
        make_filtered(), data, initial_balance=args.account_balance, pip_size=args.pip_size,
        pip_value_per_lot=args.pip_value_per_lot,
        risk_manager=RiskManager(RiskConfig(risk_per_trade_pct=args.risk_per_trade_pct, max_daily_loss_pct=100.0, max_open_positions=1)),
        is_real_account=True,
    )
    print_result(f"CON filtro ER({period})<={threshold:.4f} (realista)", signals_filtered, filtered_real)
    filtered_fixed = run_backtest(make_filtered(), data, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot)
    print_result(f"CON filtro ER({period})<={threshold:.4f} (lote fijo)", len(filtered_fixed.trades), filtered_fixed)

    reduction_pct = 100 * (1 - signals_filtered / signals_baseline) if signals_baseline else 0.0
    print(f"\nReduccion de señales por el filtro: {signals_baseline} -> {signals_filtered} ({reduction_pct:.0f}% menos)")


if __name__ == "__main__":
    main()
