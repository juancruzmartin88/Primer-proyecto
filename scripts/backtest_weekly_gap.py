"""Valida el straddle de reapertura semanal (src/weekly_gap.py) sobre un CSV historico real.

Requiere un CSV con huecos de horario genuinos entre el cierre del viernes y
la reapertura (como exporta MT5 - Symbols > Bars > Export) - un feed que
rellena el cierre de mercado con un precio congelado (Twelve Data para
XAU/USD, verificado el 27/09/2026) no detecta ninguna reapertura real. Ver
CLAUDE.md, "Evaluacion del straddle de reapertura semanal".

Acepta el formato de export de MT5 (separador tab, columnas <DATE>/<TIME> por
separado) o un CSV estandar con columna "time"/"datetime".

Uso:
    python -m scripts.backtest_weekly_gap data/xauusd_h1_full.csv \
        --min-gap-hours=20 --min-range-atr-mult=1.0 --tp-r-multiple=1.0
"""
from __future__ import annotations

import argparse

import pandas as pd

from src.indicators import atr
from src.weekly_gap import find_reopen_indices, simulate_straddle, summarize


def load_csv(path: str) -> pd.DataFrame:
    # Export de MT5: separador tab, columnas <DATE> <TIME> por separado.
    probe = pd.read_csv(path, sep=None, engine="python", nrows=1)
    columns = [c.strip("<>").lower() for c in probe.columns]

    if "date" in columns and "time" in columns and len(columns) > 2:
        df = pd.read_csv(path, sep=None, engine="python")
        df.columns = [c.strip("<>").lower() for c in df.columns]
        df["time"] = pd.to_datetime(df["date"] + " " + df["time"])
    else:
        df = pd.read_csv(path, sep=None, engine="python")
        df.columns = [c.strip().lower() for c in df.columns]
        time_col = "time" if "time" in df.columns else "datetime"
        df = df.rename(columns={time_col: "time"})
        df["time"] = pd.to_datetime(df["time"])

    df = df.sort_values("time").reset_index(drop=True)
    return df[["time", "open", "high", "low", "close"]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--min-gap-hours", type=float, default=20.0, help="Hueco minimo de horas para considerar 'reapertura' (cierre de fin de semana real).")
    parser.add_argument("--atr-period", type=int, default=100, help="Periodo del ATR de referencia (H1) para el filtro de rango minimo - ~4 dias habiles.")
    parser.add_argument("--min-range-atr-mult", type=float, default=1.0)
    parser.add_argument("--tp-r-multiple", type=float, default=1.0, help="Multiplo de riesgo para el TP (1.0 o 1.5, segun el protocolo pedido).")
    parser.add_argument("--max-lookahead", type=int, default=168, help="Velas maximas a esperar antes de descartar el straddle como no resuelto (168 = 1 semana en H1).")
    args = parser.parse_args()

    data = load_csv(args.csv_path)
    print(f"{len(data)} velas, {data['time'].iloc[0]} -> {data['time'].iloc[-1]}")

    reopen_idxs = find_reopen_indices(data, min_gap_hours=args.min_gap_hours)
    print(f"Reaperturas detectadas (hueco >= {args.min_gap_hours:.0f}hs): {len(reopen_idxs)}")
    if not reopen_idxs:
        print(
            "0 reaperturas encontradas - o el CSV no tiene huecos de horario reales "
            "(feed que rellena el cierre de mercado, no sirve para esta estrategia), "
            "o el simbolo no tiene el cierre de fin de semana esperado."
        )
        return

    atr_series = atr(data, period=args.atr_period)

    outcomes = []
    skipped_low_range = 0
    for idx in reopen_idxs:
        current_atr = atr_series.iloc[idx - 1]  # ATR hasta la vela anterior, sin mirar el futuro
        result = simulate_straddle(
            data, idx,
            current_atr=current_atr,
            min_range_atr_mult=args.min_range_atr_mult,
            tp_r_multiple=args.tp_r_multiple,
            max_lookahead=args.max_lookahead,
        )
        if result is None:
            skipped_low_range += 1
            continue
        outcomes.append(result)

    print(f"Reaperturas descartadas por rango minimo o sin ATR valido: {skipped_low_range}")
    print(f"Straddles evaluados: {len(outcomes)}\n")

    summary = summarize(outcomes)
    print(
        f"Trades resueltos: {summary['trades_resueltos']} | "
        f"Sin resolucion (ninguna pendiente se activo): {summary['sin_resolucion']} | "
        f"Win rate: {summary['win_rate']:.1%} | "
        f"Profit factor: {summary['profit_factor']:.2f} | "
        f"Total: {summary['total_r']:+.1f}R"
    )

    half = len(outcomes) // 2
    if half >= 3:
        first_half = summarize(outcomes[:half])
        second_half = summarize(outcomes[half:])
        print("\nValidacion por mitades (consistencia entre regimenes):")
        print(
            f"  1ra mitad: {first_half['trades_resueltos']} trades, "
            f"WR {first_half['win_rate']:.1%}, PF {first_half['profit_factor']:.2f}, "
            f"{first_half['total_r']:+.1f}R"
        )
        print(
            f"  2da mitad: {second_half['trades_resueltos']} trades, "
            f"WR {second_half['win_rate']:.1%}, PF {second_half['profit_factor']:.2f}, "
            f"{second_half['total_r']:+.1f}R"
        )

    print("\nDetalle por operacion:")
    for o in outcomes:
        print(f"  {o.reopen_time} | {o.direction.value} | entry={o.entry:.2f} SL={o.stop_loss:.2f} TP={o.take_profit:.2f} | {o.hit} ({o.pnl_r:+.1f}R)")


if __name__ == "__main__":
    main()
