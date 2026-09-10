"""Corre StructuralPullbackStrategy sobre un CSV y lista cada senal generada
(no solo el resultado agregado), para comparar contra un registro real de
operaciones fecha por fecha.

Uso:
    python -m scripts.list_signals data/xauusd_h1_recent.csv XAUUSD --sep=";" \
        --from=2026-08-29 --to=2026-09-10
"""
from __future__ import annotations

import argparse

import pandas as pd

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("symbol")
    parser.add_argument("--sep", default=",")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--levels-path", default="config/levels.json")
    parser.add_argument("--window-size", type=int, default=200)
    parser.add_argument("--from-date", dest="from_date", default=None)
    parser.add_argument("--to-date", dest="to_date", default=None)
    args = parser.parse_args()

    data = load_csv(args.csv_path, args.sep)
    strategy = StructuralPullbackStrategy(
        symbol=args.symbol, timeframe=args.timeframe, levels_path=args.levels_path
    )

    print(f"{args.symbol}: {len(data)} velas, {data['time'].iloc[0]} -> {data['time'].iloc[-1]}")
    signals_found = 0
    for i in range(strategy.min_history, len(data)):
        window = data.iloc[max(0, i + 1 - args.window_size) : i + 1]
        candle = data.iloc[i]
        if args.from_date and candle["time"] < pd.Timestamp(args.from_date):
            continue
        if args.to_date and candle["time"] > pd.Timestamp(args.to_date):
            continue

        signal = strategy.generate_signal(window)
        if signal in (Signal.BUY, Signal.SELL):
            sl = strategy.stop_loss_price(window, signal)
            tp = strategy.take_profit_price(window, signal)
            signals_found += 1
            print(
                f"  {candle['time']} | {signal.value:4s} | entry={candle['close']:.2f} "
                f"| SL={sl:.2f} | TP={tp:.2f}"
            )

    if signals_found == 0:
        print("  (ninguna senal en el rango pedido)")


if __name__ == "__main__":
    main()
