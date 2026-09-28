"""Ventana de sincronizacion entre el toque de RSI extremo y la vela de
rechazo (28/09/2026) - evaluacion puntual sobre BTC.

Surge del diagnostico de la sequia de 2 semanas en BTC (28/09/2026, ver
CLAUDE.md "Diagnóstico de régimen de mercado en BTC"): en 33 casos con vela
de rechazo geometricamente valida desde el 16/09, ninguno coincidio con un
RSI genuinamente extremo en el mismo momento - 29 porque el RSI no habia
tocado 35/65 todavia (esos siguen sin calificar aca, no es lo que se
prueba), y 4 porque el RSI habia tocado el extremo pero **todavia no habia
girado de vuelta** (`rsi_confirmacion` seguia del lado extremo) para el
momento en que aparecio la vela de rechazo/confirmacion.

`StructuralPullbackStrategy._rsi_extreme_and_turn` exige las dos cosas a la
vez: que el RSI haya tocado el extremo en una ventana de `extreme_lookback`
velas, Y que para la vela de CONFIRMACION ya haya vuelto a cruzar el
umbral (`rsi_confirmacion > oversold` / `< overbought`). `SyncWindowStrategy`
reemplaza esa segunda condicion: en vez de exigir el cruce de vuelta ya
confirmado, exige que la vela de RECHAZO aparezca dentro de `sync_window`
velas despues del ultimo toque del extremo (nunca antes - la vela de
rechazo no puede "adelantarse" a un toque que todavia no paso, eso seria
perseguir impulso). Todo lo demas (nivel, vela de rechazo geometrica,
vela de confirmacion, volumen, SL/TP) queda exactamente igual, heredado
sin tocar de `StructuralPullbackStrategy`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.strategies.structural_pullback import StructuralPullbackStrategy
from src.types import Signal


class SyncWindowStrategy(StructuralPullbackStrategy):
    def __init__(self, *args, sync_window: int = 2, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.sync_window = sync_window

    def _rsi_extreme_and_turn(
        self, rsi_series: pd.Series, rejection_idx: int, confirmation_idx: int, direction: Signal
    ) -> bool:
        window_start = max(0, confirmation_idx - self.extreme_lookback)
        window_values = rsi_series.iloc[window_start : rejection_idx + 1].to_numpy()
        if window_values.size == 0 or np.isnan(window_values).all():
            return False

        if direction == Signal.BUY:
            touched = window_values <= self.rsi_oversold
        else:
            touched = window_values >= self.rsi_overbought

        if not touched.any():
            return False

        # Posicion absoluta (misma base que rejection_idx/confirmation_idx)
        # del ultimo toque del extremo dentro de la ventana de busqueda.
        last_touch_offset = np.where(touched)[0].max()
        last_touch_idx = window_start + last_touch_offset

        # "no antes": last_touch_idx <= rejection_idx siempre (la ventana de
        # busqueda ya termina en rejection_idx), asi que solo falta exigir
        # que no haya pasado demasiado tiempo desde el toque.
        return (rejection_idx - last_touch_idx) <= self.sync_window
