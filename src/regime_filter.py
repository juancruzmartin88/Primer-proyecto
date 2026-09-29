"""Filtro de regimen dinamico sobre la Metodologia v2 en BTC (30/09/2026) -
evaluacion puntual. v2 tiene PF 1.77 (realista) en BTC, pero es una
estrategia de REVERSION (entra contra un extremo de RSI) - la sospecha del
usuario es que rinde peor cuando el mercado esta en tendencia fuerte
sostenida (el precio sigue de largo en vez de revertir, y la señal de
reversion termina en SL). Los diagnosticos de regimen de Oro y BTC
(28/09/2026) ya usaron Efficiency Ratio de Kaufman como lectura, no como
filtro activo - esto lo convierte en filtro real: descarta a HOLD
cualquier señal cruda de v2 cuya ER(periodo) en el momento de la señal
supere un techo (`er_ceiling`), sin importar que RSI/vela de rechazo
hayan sido validos.

`RegimeFilteredStrategy` envuelve `StructuralPullbackStrategy` sin
tocarla - mismo patron que `VolatilityFilteredStrategy`/
`TrendFilteredStrategy`, pero con un TECHO en vez de un piso (acá se
descarta la tendencia FUERTE, no la volatilidad baja). Usa el ER sobre la
misma ventana que ya recibe `generate_signal` (sin lookahead: el valor en
la vela t solo usa datos hasta t).
"""
from __future__ import annotations

import pandas as pd

from src.indicators import efficiency_ratio
from src.strategy_base import Strategy
from src.types import Signal


class RegimeFilteredStrategy(Strategy):
    def __init__(self, base: Strategy, *, er_ceiling: float, er_period: int = 14) -> None:
        self.base = base
        self.er_ceiling = er_ceiling
        self.er_period = er_period
        self.symbol = base.symbol
        self.timeframe = base.timeframe
        self.min_history = getattr(base, "min_history", 0)

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        signal = self.base.generate_signal(data)
        if signal not in (Signal.BUY, Signal.SELL):
            return signal
        er_series = efficiency_ratio(data["close"], period=self.er_period)
        current_er = er_series.iloc[-1]
        if pd.isna(current_er) or current_er > self.er_ceiling:
            return Signal.HOLD
        return signal

    def stop_loss_price(self, data: pd.DataFrame, signal: Signal) -> float:
        return self.base.stop_loss_price(data, signal)

    def take_profit_price(self, data: pd.DataFrame, signal: Signal) -> float:
        return self.base.take_profit_price(data, signal)
