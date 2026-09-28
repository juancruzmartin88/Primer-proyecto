"""Evalua un techo de riesgo mas alto (ej. 3%) para Oro (28/09/2026).

Compara, sobre el mismo benchmark de siempre, cuantas señales de Oro se
desbloquean si el riesgo objetivo sube de 1-2% al valor pedido, manteniendo
todo lo demas igual (misma Metodologia v2, mismo lote minimo, mismo modo
"realista" que bloquea en cuenta real). Reporta trades, win rate, profit
factor, drawdown y la peor racha de perdidas consecutivas en dolares sobre
el capital indicado.

Uso:
    python -m scripts.backtest_risk_ceiling data/xauusd_h1_raw.csv XAUUSD \
        --sep=";" --account-balance=715.24 --baseline-risk-pct=2.0 --higher-risk-pct=3.0
"""
from __future__ import annotations

import argparse

import pandas as pd
from loguru import logger

from src.backtester import BacktestResult, run_backtest
from src.config import RiskConfig
from src.risk_manager import RiskManager
from src.strategies.structural_pullback import StructuralPullbackStrategy


def load_csv(path: str, sep: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=sep)
    df.columns = [c.strip().lower() for c in df.columns]
    time_col = "time" if "time" in df.columns else "datetime"
    df = df.rename(columns={time_col: "time"})
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)
    return df[["time", "open", "high", "low", "close"]]


def run_at_risk(data, symbol, levels_path, *, account_balance, risk_pct, pip_size, pip_value_per_lot) -> BacktestResult:
    strategy = StructuralPullbackStrategy(symbol=symbol, timeframe="H1", levels_path=levels_path)
    risk_manager = RiskManager(RiskConfig(risk_per_trade_pct=risk_pct, max_daily_loss_pct=100.0, max_open_positions=1))
    return run_backtest(
        strategy, data, initial_balance=account_balance, pip_size=pip_size, pip_value_per_lot=pip_value_per_lot,
        risk_manager=risk_manager, is_real_account=True,
    )


def print_result(label: str, result: BacktestResult) -> None:
    streak = result.worst_losing_streak
    print(f"[{label}] {result.summary()}")
    print(f"    Peor racha de perdidas consecutivas: {streak['count']} operaciones, ${streak['amount']:+.2f}")
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
    parser.add_argument("--baseline-risk-pct", type=float, default=2.0)
    parser.add_argument("--higher-risk-pct", type=float, default=3.0)
    parser.add_argument("--pip-size", type=float, default=0.01)
    parser.add_argument("--pip-value-per-lot", type=float, default=1.0)
    args = parser.parse_args()

    logger.remove()  # suprime el debug/warning de RiskManager - son miles de lineas en una corrida asi

    data = load_csv(args.csv_path, args.sep)
    print(f"{args.symbol}: {len(data)} velas, {data['time'].iloc[0]} -> {data['time'].iloc[-1]}\n")

    baseline = run_at_risk(
        data, args.symbol, args.levels_path, account_balance=args.account_balance,
        risk_pct=args.baseline_risk_pct, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot,
    )
    print_result(f"Riesgo {args.baseline_risk_pct:.1f}% (baseline)", baseline)
    print()

    higher = run_at_risk(
        data, args.symbol, args.levels_path, account_balance=args.account_balance,
        risk_pct=args.higher_risk_pct, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot,
    )
    print_result(f"Riesgo {args.higher_risk_pct:.1f}%", higher)
    print()

    print(
        f"Señales adicionales desbloqueadas: {len(higher.trades) - len(baseline.trades)} "
        f"({len(baseline.trades)} -> {len(higher.trades)})"
    )


if __name__ == "__main__":
    main()
