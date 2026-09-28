"""Filtro de piso de volatilidad sobre la Metodologia v2 (28/09/2026) - evaluacion puntual.

Surge del diagnostico de la inconsistencia entre mitades de Oro: la
segunda mitad del periodo de referencia no fue mas volatil, fue mas
lateral y comprimida (ATR -25%, Efficiency Ratio 4x menor) - la cantidad
de reversiones genuinas (salidas por TP) fue identica en las dos mitades,
pero el regimen comprimido genero señales falsas adicionales que fueron
directo a SL. Hipotesis a probar: descartar una señal de reversion si el
ATR(14) en 1H al momento de la señal esta por debajo de un piso, en vez de
filtrar por direccion (lo que ya se probo y fallo, ver src/trend_filter.py).

`VolatilityFilteredStrategy` envuelve `StructuralPullbackStrategy` sin
tocarla - mismo patron que `TrendFilteredStrategy`. Usa el mismo ATR(14)
trailing que ya calcula la estrategia base internamente para su propio SL,
asi que no hay lookahead: el valor en la vela t solo usa datos hasta t.
"""
from __future__ import annotations

import pandas as pd

from src.indicators import atr
from src.strategy_base import Strategy
from src.types import Signal


class VolatilityFilteredStrategy(Strategy):
    def __init__(self, base: Strategy, *, atr_floor: float, atr_period: int = 14) -> None:
        self.base = base
        self.atr_floor = atr_floor
        self.atr_period = atr_period
        self.symbol = base.symbol
        self.timeframe = base.timeframe
        self.min_history = getattr(base, "min_history", 0)

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        signal = self.base.generate_signal(data)
        if signal not in (Signal.BUY, Signal.SELL):
            return signal
        atr_series = atr(data, period=self.atr_period)
        current_atr = atr_series.iloc[-1]
        if pd.isna(current_atr) or current_atr < self.atr_floor:
            return Signal.HOLD
        return signal

    def stop_loss_price(self, data: pd.DataFrame, signal: Signal) -> float:
        return self.base.stop_loss_price(data, signal)

    def take_profit_price(self, data: pd.DataFrame, signal: Signal) -> float:
        return self.base.take_profit_price(data, signal)
