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
from src.strategies.structural_pullback import StructuralPullbackStrategy


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
    args = parser.parse_args()

    data = load_csv(args.csv_path, args.sep)
    strategy = StructuralPullbackStrategy(
        symbol=args.symbol, timeframe=args.timeframe, levels_path=args.levels_path
    )
    result = run_backtest(
        strategy,
        data,
        pip_size=args.pip_size,
        pip_value_per_lot=args.pip_value_per_lot,
    )

    print(f"{args.symbol}: {len(data)} velas, {data['time'].iloc[0]} -> {data['time'].iloc[-1]}")
    print(result.summary())


if __name__ == "__main__":
    main()
