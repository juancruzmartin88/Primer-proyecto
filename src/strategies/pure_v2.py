"""Metodologia v2 "pura" (sin vela de confirmacion extra, SL ajustado) - evaluacion puntual (28/09/2026).

Surge del diagnostico del 24/09/2026 (ver CLAUDE.md, "Diferencia entre
operaciones manuales y detección del bot en Oro"): el bot en produccion
(`StructuralPullbackStrategy`) es mas estricto que el analisis manual del
usuario en dos puntos especificos, ninguno de los cuales esta pedido
explicitamente por la seccion 4 del sistema documentado:

  1. Exige una vela de CONFIRMACION adicional (la vela siguiente a la de
     rechazo, cerrando a favor) antes de entrar - un candle mas de espera
     que el criterio manual, que opera directo sobre la vela de
     rechazo/giro.
  2. Calcula el SL como el minimo/maximo de una VENTANA de 8 velas de
     pullback (menos margen de ATR), en vez del punto tecnico mas ajustado
     posible - el extremo de la vela de rechazo misma.

`PureV2Strategy` hereda de `StructuralPullbackStrategy` y reutiliza toda su
logica (niveles, RSI extremo+giro, patron de vela de rechazo, volumen) sin
tocarla - solo sobreescribe `_analyze` para:

  - Actuar directamente sobre la vela de rechazo (la ultima vela cerrada),
    sin esperar una vela de confirmacion siguiente. El "giro ya confirmado"
    de RSI (puntos 2/3 de la seccion 4) se evalua con esa misma vela como
    referencia, en vez de la vela de confirmacion separada.
  - Calcular el SL contra el extremo de esa unica vela de rechazo (mas el
    mismo margen de ATR que ya usa la estrategia base), en vez de la
    ventana completa de `lookback_candles`.

Nada mas cambia: mismo umbral RSI 35/65, mismo test geometrico de vela de
rechazo (`is_hammer`/`is_shooting_star`), mismo filtro de nivel estructural
y de volumen, mismo calculo de TP. El objetivo es aislar el efecto de esos
dos criterios puntuales, no evaluar una estrategia distinta.
"""
from __future__ import annotations

import pandas as pd

from src.indicators import atr, rsi
from src.levels import get_levels_for_symbol
from src.strategies.structural_pullback import StructuralPullbackStrategy, _Setup
from src.types import Signal


class PureV2Strategy(StructuralPullbackStrategy):
    def _analyze(self, data: pd.DataFrame) -> _Setup | None:
        levels = get_levels_for_symbol(self.symbol, data, manual_levels_path=self.levels_path)
        if not levels:
            return None

        atr_series = atr(data, period=self.atr_period)
        current_atr = atr_series.iloc[-1]
        if pd.isna(current_atr) or current_atr <= 0:
            return None

        rsi_series = rsi(data["close"], period=self.rsi_period)
        volume_series = self._volume_series(data)

        rejection_idx = len(data) - 1
        if rejection_idx < 1:
            return None
        rejection = data.iloc[rejection_idx]

        for direction in (Signal.BUY, Signal.SELL):
            if not self._is_rejection_candle(rejection, direction):
                continue
            # Sin vela de confirmacion separada: el "giro ya confirmado" se
            # evalua con la propia vela de rechazo como referencia.
            if not self._rsi_extreme_and_turn(rsi_series, rejection_idx, rejection_idx, direction):
                continue
            if not self._volume_confirmed(volume_series, rejection_idx):
                continue

            level = self._find_pullback_level(data, levels, rejection_idx, direction, current_atr)
            if level is None:
                continue

            stop_loss = self._calculate_stop_loss_pure(rejection, direction, current_atr)
            entry_price = rejection["close"]
            take_profit = self._calculate_take_profit(levels, entry_price, direction, stop_loss)

            return _Setup(signal=direction, stop_loss=stop_loss, take_profit=take_profit)

        return None

    def _calculate_stop_loss_pure(self, rejection: pd.Series, direction: Signal, current_atr: float) -> float:
        margin = self.sl_atr_margin_mult * current_atr
        if direction == Signal.BUY:
            return rejection["low"] - margin
        return rejection["high"] + margin
