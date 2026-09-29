"""Variante de v3 (tendencia con pullback a EMA) con vela de confirmacion
extra, BTC (30/09/2026) - evaluacion puntual.

v3 (`src/strategies/trend_pullback.py`) fue rechazada dos veces en BTC
(EMA 50 el 29/09, PF 0.98 realista; EMA 21 el mismo dia, PF 1.01) sin que
acortar el periodo de la EMA cambiara nada de fondo. Hipotesis del
usuario: v3 nunca exigio la vela de confirmacion que si tiene v2 (cierre
de la vela SIGUIENTE a la de rechazo, a favor de la direccion) - y ya se
demostro (`src/strategies/pure_v2.py`, "Metodologia v2 pura para BTC",
28/09/2026) que sacarle esa misma exigencia a v2 hunde su profit factor de
1.71 a 0.91. Si la confirmacion sostiene el profit factor de v2, podria
estar sosteniendo tambien el de v3 - BTC es un activo lo bastante volatil
como para que un "pullback" que parece limpio en la vela de rechazo sola
resulte, en varios casos, el arranque de una reversion genuina en vez de
una continuacion, y la vela siguiente lo delata.

Unico cambio respecto a `TrendPullbackStrategy`: la entrada ya no ocurre
en la propia vela de rechazo, sino en la vela SIGUIENTE, y solo si esa
vela cierra a favor de la direccion de la tendencia (mismo criterio que
`StructuralPullbackStrategy._is_confirmation_candle`: cierre > apertura
para BUY, cierre < apertura para SELL, sin exigencia extra sobre cuanto).
Todo lo demas - EMA de tendencia, proximidad del pullback, geometria de
la vela de rechazo, SL detras de su extremo, TP por nivel/fallback - queda
igual, solo se recalculan los indices porque la vela de rechazo pasa a
ser la anteultima, no la ultima.
"""
from __future__ import annotations

import pandas as pd

from src.candles import is_hammer, is_shooting_star
from src.indicators import atr, ema
from src.levels import get_levels_for_symbol
from src.strategies.trend_pullback import TrendPullbackStrategy, _Setup
from src.types import Signal


class TrendPullbackConfirmedStrategy(TrendPullbackStrategy):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Una vela mas de historia: la de rechazo ya no es la ultima, hace
        # falta una adicional para la confirmacion.
        self.min_history += 1

    def _analyze(self, data: pd.DataFrame) -> _Setup | None:
        confirmation_idx = len(data) - 1
        rejection_idx = confirmation_idx - 1
        trend_start = rejection_idx - self.trend_confirmation_candles
        if trend_start < 0:
            return None

        ema_series = ema(data["close"], period=self.ema_period)
        current_ema = ema_series.iloc[rejection_idx]
        trend_emas = ema_series.iloc[trend_start:rejection_idx]
        if pd.isna(current_ema) or trend_emas.isna().any():
            return None

        trend_closes = data["close"].iloc[trend_start:rejection_idx]
        uptrend = (trend_closes > trend_emas).all()
        downtrend = (trend_closes < trend_emas).all()
        if not uptrend and not downtrend:
            return None

        atr_series = atr(data, period=self.atr_period)
        current_atr = atr_series.iloc[rejection_idx]
        if pd.isna(current_atr) or current_atr <= 0:
            return None

        rejection = data.iloc[rejection_idx]
        confirmation = data.iloc[confirmation_idx]
        proximity = self.level_proximity_atr_mult * current_atr
        entry_price = confirmation["close"]
        levels = get_levels_for_symbol(self.symbol, data, manual_levels_path=self.levels_path)

        if uptrend:
            if not is_hammer(rejection, min_wick_to_body=self.rejection_wick_ratio):
                return None
            if confirmation["close"] <= confirmation["open"]:
                return None
            if abs(rejection["low"] - current_ema) > proximity:
                return None
            stop_loss = rejection["low"] - self.sl_atr_margin_mult * current_atr
            take_profit = self._calculate_take_profit(levels, entry_price, Signal.BUY, stop_loss)
            if stop_loss < entry_price < take_profit:
                return _Setup(signal=Signal.BUY, stop_loss=stop_loss, take_profit=take_profit)
            return None

        if not is_shooting_star(rejection, min_wick_to_body=self.rejection_wick_ratio):
            return None
        if confirmation["close"] >= confirmation["open"]:
            return None
        if abs(rejection["high"] - current_ema) > proximity:
            return None
        stop_loss = rejection["high"] + self.sl_atr_margin_mult * current_atr
        take_profit = self._calculate_take_profit(levels, entry_price, Signal.SELL, stop_loss)
        if take_profit < entry_price < stop_loss:
            return _Setup(signal=Signal.SELL, stop_loss=stop_loss, take_profit=take_profit)
        return None
