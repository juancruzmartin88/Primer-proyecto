"""Corre StructuralPullbackStrategy sobre un CSV de velas historicas.

Acepta tanto el formato que devuelve Twelve Data (separador ";", columna
"datetime", orden descendente) como un CSV estandar con columnas
time,open,high,low,close en orden cronologico ascendente.

Uso:
    python -m scripts.backtest_from_csv data/xauusd_h1_raw.csv XAUUSD \
        --sep=";" --pip-size=0.01 --pip-value-per-lot=1.0
"""
from __future__ import annotations

import argparse

import pandas as pd

from src.backtester import run_backtest
from src.config import RiskConfig
from src.risk_manager import RiskManager
from src.strategies.structural_pullback import StructuralPullbackStrategy
from src.time_exit import DEFAULT_MAX_HOURS_OPEN, DEFAULT_STALL_ATR_MULT


def load_csv(path: str, sep: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=sep)
    df.columns = [c.strip().lower() for c in df.columns]
    time_col = "time" if "time" in df.columns else "datetime"
    df = df.rename(columns={time_col: "time"})
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)  # Twelve Data viene mas reciente primero
    return df[["time", "open", "high", "low", "close"]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("symbol")
    parser.add_argument("--sep", default=",")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--pip-size", type=float, default=0.0001)
    parser.add_argument("--pip-value-per-lot", type=float, default=10.0)
    parser.add_argument("--levels-path", default="config/levels.json")
    parser.add_argument("--account-balance", type=float, default=650.0)
    parser.add_argument("--risk-per-trade-pct", type=float, default=2.0)
    parser.add_argument("--min-lot", type=float, default=0.01)
    parser.add_argument("--rejection-wick-ratio", type=float, default=1.5)
    parser.add_argument("--is-real-account", action="store_true", help="Bloquea señales cuyo lote minimo fuerce mas riesgo del objetivo (seccion 3.2), igual que la cuenta real.")
    parser.add_argument("--enable-time-exit", action="store_true", help="Simula el limite de tiempo maximo (seccion 6.1) sobre las operaciones abiertas.")
    parser.add_argument("--max-hours-open", type=float, default=DEFAULT_MAX_HOURS_OPEN)
    parser.add_argument("--stall-atr-mult", type=float, default=DEFAULT_STALL_ATR_MULT)
    args = parser.parse_args()

    data = load_csv(args.csv_path, args.sep)
    print(f"{args.symbol}: {len(data)} velas, {data['time'].iloc[0]} -> {data['time'].iloc[-1]}")

    # 1) Lote fijo: aisla la calidad de las senales, pero el drawdown en
    #    USD/% no es realista (no refleja tu riesgo real por operacion).
    strategy = StructuralPullbackStrategy(
        symbol=args.symbol,
        timeframe=args.timeframe,
        levels_path=args.levels_path,
        rejection_wick_ratio=args.rejection_wick_ratio,
    )
    fixed_lot_result = run_backtest(
        strategy, data, pip_size=args.pip_size, pip_value_per_lot=args.pip_value_per_lot
    )
    print(f"[Lote fijo 1.0]      {fixed_lot_result.summary()}")

    # 2) Riesgo real: mismo RiskManager que usa el bot en vivo, sobre un
    #    balance inicial y % de riesgo por operacion configurables.
    strategy_for_risk = StructuralPullbackStrategy(
        symbol=args.symbol,
        timeframe=args.timeframe,
        levels_path=args.levels_path,
        rejection_wick_ratio=args.rejection_wick_ratio,
    )
    risk_manager = RiskManager(
        RiskConfig(
            risk_per_trade_pct=args.risk_per_trade_pct,
            max_daily_loss_pct=100.0,  # el backtest no simula el kill switch diario
            max_open_positions=1,
        )
    )
    risk_based_result = run_backtest(
        strategy_for_risk,
        data,
        initial_balance=args.account_balance,
        pip_size=args.pip_size,
        pip_value_per_lot=args.pip_value_per_lot,
        risk_manager=risk_manager,
        min_lot=args.min_lot,
        is_real_account=args.is_real_account,
        enable_time_exit=args.enable_time_exit,
        max_hours_open=args.max_hours_open,
        stall_atr_mult=args.stall_atr_mult,
    )
    tag = "real" if args.is_real_account else "exploratorio"
    time_tag = f", limite {args.max_hours_open:.0f}hs" if args.enable_time_exit else ""
    print(
        f"[Riesgo {args.risk_per_trade_pct:.1f}% sobre ${args.account_balance:.0f}, {tag}{time_tag}] "
        f"{risk_based_result.summary()}"
    )


if __name__ == "__main__":
    main()
