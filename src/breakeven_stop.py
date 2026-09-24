"""Regla de stop a breakeven (evaluada 24/09/2026, NO activa por defecto).

Pedido del usuario: cuando una posicion abierta alcanza X% de la distancia
entre la entrada y el Take Profit (a favor), mover el Stop Loss al precio
de entrada + un margen fijo (para cubrir spread/comision) - una sola vez,
no un trailing continuo como el evaluado para `BreakoutStrategy`
(`src/strategies/breakout.py`). No modifica ninguna logica de entrada de
la Metodologia v2 - es una regla de gestion de la salida, aplicable tanto a
BTC como a Oro por igual.

Logica pura (sin dependencias de MT5/backtester), para poder testearla
aislada y reusarla tanto en produccion (`src/bot.py`) como en el backtest
(`src/backtester.py`).
"""
from __future__ import annotations

from src.types import Signal

DEFAULT_TRIGGER_PCT = 0.5
DEFAULT_BREAKEVEN_BUFFER = 1.0


def breakeven_stop_price(
    *,
    direction: Signal,
    entry_price: float,
    take_profit_price: float,
    favorable_price: float,
    trigger_pct: float = DEFAULT_TRIGGER_PCT,
    buffer: float = DEFAULT_BREAKEVEN_BUFFER,
) -> float | None:
    """Nuevo SL a breakeven si ya se alcanzo el umbral, o None si todavia no.

    `favorable_price` es el precio mas favorable alcanzado hasta el
    momento (el high de la vela para una posicion BUY, el low para SELL) -
    no el cierre, para no perderse un toque intra-vela. El umbral se mide
    como % de la distancia ORIGINAL entre entrada y TP (no se recalcula si
    el TP cambia), tal como lo pidio el usuario ("X% de la distancia al
    Take Profit").
    """
    reward_distance = abs(take_profit_price - entry_price)
    if reward_distance <= 0:
        return None
    if direction == Signal.BUY:
        favorable_move = favorable_price - entry_price
        if favorable_move < trigger_pct * reward_distance:
            return None
        return entry_price + buffer
    favorable_move = entry_price - favorable_price
    if favorable_move < trigger_pct * reward_distance:
        return None
    return entry_price - buffer
