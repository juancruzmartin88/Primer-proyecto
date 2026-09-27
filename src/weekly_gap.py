"""Straddle sobre la vela de reapertura semanal (24/09/2026) - caso puntual.

Idea propuesta por el usuario (consultada en paralelo con otro chat), SEPARADA
de la Metodologia v2: en la primera vela H1 tras la reapertura del mercado
(domingo a la noche hora Argentina/Exness), colocar Buy Stop sobre el maximo
de esa vela y Sell Stop bajo el minimo (OCO - la que se dispara primero
cancela la otra), dejando que el precio confirme la direccion en vez de
adivinarla. SL en el extremo opuesto de la misma vela. TP a un multiplo fijo
del riesgo (1x o 1.5x, no un nivel estructural). Filtro: solo operar si el
rango de esa vela supera un ATR de referencia (para descartar reaperturas
"chatas" sin informacion real).

Logica pura, sin I/O - separada de src/backtester.py porque el mecanismo
(dos ordenes pendientes simultaneas, resultado en multiplos de riesgo fijo,
no en dolares con lote/riesgo del RiskManager) no encaja en el motor de
backtest de una sola estrategia por vela que ya usa el resto del proyecto.
Este modulo no calcula PnL en dolares - los resultados son en R (multiplos
de riesgo), consistente con el protocolo de validacion que pidio el usuario
(Profit Factor, no PnL absoluto).

IMPORTANTE sobre datos (ver CLAUDE.md, "Evaluacion del straddle de
reapertura semanal"): `find_reopen_indices` necesita que el DataFrame tenga
huecos de horario GENUINOS entre el cierre del viernes y la reapertura -
como los que exporta MT5 (las velas de fin de semana simplemente no
existen). Un feed que rellena el cierre de mercado con un precio congelado
en vez de dejar el hueco (Twelve Data para XAU/USD, verificado el
27/09/2026) no sirve de entrada aca - la deteccion de reapertura fallaria
en silencio (0 velas encontradas) o, peor, tomaria una vela sin sentido.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.types import Signal


@dataclass(frozen=True)
class GapTradeOutcome:
    reopen_time: pd.Timestamp
    direction: Signal
    entry: float
    stop_loss: float
    take_profit: float
    exit_price: float
    pnl_r: float  # en multiplos de riesgo (R) - este modulo no sabe de lotes/dolares
    hit: str  # "tp" | "sl" | "no_resolution" (ninguna pendiente se activo a tiempo)


def find_reopen_indices(data: pd.DataFrame, *, min_gap_hours: float = 20.0) -> list[int]:
    """Indices de velas que arrancan tras un hueco real de >= min_gap_hours.

    Requiere timestamps con huecos genuinos (velas de fin de semana ausentes,
    como exporta MT5) - ver advertencia del modulo sobre feeds que rellenan
    el cierre de mercado con un precio congelado en vez de dejar el hueco.
    """
    if len(data) < 2:
        return []
    gaps = data["time"].diff().dt.total_seconds() / 3600.0
    return [i for i in range(1, len(data)) if gaps.iloc[i] >= min_gap_hours]


def simulate_straddle(
    data: pd.DataFrame,
    reopen_idx: int,
    *,
    current_atr: float,
    min_range_atr_mult: float = 1.0,
    tp_r_multiple: float = 1.0,
    max_lookahead: int = 168,
) -> GapTradeOutcome | None:
    """Simula el straddle Buy Stop/Sell Stop sobre la vela en `reopen_idx`.

    Devuelve None si la vela no supera el filtro de rango minimo, o si
    ninguna de las dos pendientes llega a activarse dentro de
    `max_lookahead` velas (por defecto, una semana de H1).
    """
    reopen = data.iloc[reopen_idx]
    if pd.isna(current_atr) or current_atr <= 0:
        return None
    candle_range = reopen["high"] - reopen["low"]
    if candle_range < min_range_atr_mult * current_atr:
        return None

    entry_high = reopen["high"]
    entry_low = reopen["low"]

    direction: Signal | None = None
    entry_price = 0.0
    stop_loss = 0.0
    take_profit = 0.0

    end = min(len(data), reopen_idx + 1 + max_lookahead)
    for i in range(reopen_idx + 1, end):
        candle = data.iloc[i]

        if direction is None:
            triggers_up = candle["high"] >= entry_high
            triggers_down = candle["low"] <= entry_low
            if triggers_up and triggers_down:
                # Vela rara que toca los dos niveles a la vez (sin datos de
                # tick no se puede saber cual fue primero) - aproximacion:
                # el nivel mas cercano al open de esa vela se activo antes.
                dist_up = abs(candle["open"] - entry_high)
                dist_down = abs(candle["open"] - entry_low)
                triggers_up, triggers_down = dist_up <= dist_down, dist_up > dist_down
            if triggers_up:
                direction = Signal.BUY
                entry_price, stop_loss = entry_high, entry_low
            elif triggers_down:
                direction = Signal.SELL
                entry_price, stop_loss = entry_low, entry_high
            else:
                continue
            risk = abs(entry_price - stop_loss)
            take_profit = (
                entry_price + tp_r_multiple * risk
                if direction == Signal.BUY
                else entry_price - tp_r_multiple * risk
            )
            continue

        hit_sl = candle["low"] <= stop_loss if direction == Signal.BUY else candle["high"] >= stop_loss
        hit_tp = candle["high"] >= take_profit if direction == Signal.BUY else candle["low"] <= take_profit
        if hit_sl or hit_tp:
            # SL con prioridad si se tocan los dos en la misma vela - mismo
            # criterio conservador que usa run_backtest() en src/backtester.py.
            if hit_sl:
                return GapTradeOutcome(
                    reopen_time=reopen["time"], direction=direction, entry=entry_price,
                    stop_loss=stop_loss, take_profit=take_profit, exit_price=stop_loss,
                    pnl_r=-1.0, hit="sl",
                )
            return GapTradeOutcome(
                reopen_time=reopen["time"], direction=direction, entry=entry_price,
                stop_loss=stop_loss, take_profit=take_profit, exit_price=take_profit,
                pnl_r=tp_r_multiple, hit="tp",
            )

    if direction is None:
        return None  # ninguna de las dos pendientes se activo en la ventana
    return GapTradeOutcome(
        reopen_time=reopen["time"], direction=direction, entry=entry_price,
        stop_loss=stop_loss, take_profit=take_profit, exit_price=data.iloc[end - 1]["close"],
        pnl_r=0.0, hit="no_resolution",
    )


def summarize(outcomes: list[GapTradeOutcome]) -> dict:
    """Profit factor y win rate en R - protocolo de validacion pedido por el usuario."""
    resolved = [o for o in outcomes if o.hit in ("tp", "sl")]
    wins = [o for o in resolved if o.pnl_r > 0]
    losses = [o for o in resolved if o.pnl_r < 0]
    gross_profit = sum(o.pnl_r for o in wins)
    gross_loss = abs(sum(o.pnl_r for o in losses))
    if gross_loss == 0:
        profit_factor = float("inf") if gross_profit > 0 else 0.0
    else:
        profit_factor = gross_profit / gross_loss
    return {
        "reopens_totales": len(outcomes),
        "trades_resueltos": len(resolved),
        "sin_resolucion": len(outcomes) - len(resolved),
        "win_rate": (len(wins) / len(resolved)) if resolved else 0.0,
        "profit_factor": profit_factor,
        "total_r": sum(o.pnl_r for o in resolved),
    }
