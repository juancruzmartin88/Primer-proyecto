"""Regla de tiempo maximo para posiciones abiertas (seccion 6.1 del
sistema, agregada 17/09/2026).

Motivo (historial real): una operacion de corto plazo en BTC (entrada
post-Fed el 16/09) quedo abierta casi 24 horas sin acercarse ni al TP ni al
SL - lateralizando en un rango angosto - y termino cerrandose manual en
apenas +$0,47 sobre un riesgo planeado de -$7,33. Tiempo inmovilizado sin
necesidad, y mientras tanto otras señales (en el mismo instrumento u Oro)
pueden pasar desapercibidas por falta de atencion.

Esta regla NO es parte de la logica de entrada de la Metodologia v2 - es
una salida por criterio de gestion (seccion 6.1: "no invalida la señal
original ni cuenta como error de proceso").

El documento distingue "corto plazo" (limite de 4hs) de "mediano/largo
plazo" (sin limite fijo), pero el bot unifico esa distincion el 14/09/2026
(un solo riesgo, una sola logica de entrada, todo en H1 - ver CLAUDE.md).
Como consecuencia, TODAS las posiciones que abre el bot caen bajo la rama
"corto plazo" de la seccion 6.1: se les aplica el umbral de 4 horas.
"""
from __future__ import annotations

from datetime import datetime

from src.types import Signal

DEFAULT_MAX_HOURS_OPEN = 4.0
DEFAULT_STALL_ATR_MULT = 0.5


def should_force_close(
    *,
    direction: Signal,
    entry_price: float,
    entry_time: datetime,
    current_time: datetime,
    current_price: float,
    current_rsi: float,
    current_atr: float,
    max_hours_open: float = DEFAULT_MAX_HOURS_OPEN,
    stall_atr_mult: float = DEFAULT_STALL_ATR_MULT,
) -> bool:
    """True si la posicion abierta tiene que cerrarse por limite de tiempo.

    Antes de `max_hours_open` nunca fuerza el cierre (seccion 6.1: "limite
    de 4 horas desde la activacion" para corto plazo). Una vez superado ese
    umbral, la posicion se sigue sosteniendo SOLO si se cumplen a la vez
    las dos condiciones que pide la seccion 6.1 para "dar mas margen":

      - el RSI todavia sostiene el lado de la tesis (>50 para compras, <50
        para ventas), y
      - el precio ya se movio a favor una distancia significativa - se
        aproxima "sin lateralizar en un rango angosto" como un avance a
        favor de al menos `stall_atr_mult` * ATR actual desde la entrada
        (0.5x por defecto: medio rango promedio de vela, un piso bajo a
        proposito para no cerrar operaciones que solo estan siendo lentas).

    Si cualquiera de las dos falla (el RSI perdio el lado, o el precio no
    se movio lo suficiente en ninguna direccion), se fuerza el cierre - sea
    con ganancia, perdida o breakeven, tal como pide la seccion 6.1 ("no
    esperar una vela mas indefinidamente").
    """
    hours_open = (current_time - entry_time).total_seconds() / 3600.0
    if hours_open < max_hours_open:
        return False

    rsi_favorable = current_rsi > 50 if direction == Signal.BUY else current_rsi < 50
    favorable_move = (
        current_price - entry_price if direction == Signal.BUY else entry_price - current_price
    )
    stalled = current_atr <= 0 or favorable_move < stall_atr_mult * current_atr

    return not (rsi_favorable and not stalled)
