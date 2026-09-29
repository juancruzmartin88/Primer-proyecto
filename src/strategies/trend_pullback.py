"""Tendencia con pullback a media movil, Oro (28-29/09/2026) - evaluacion
puntual, sistema SEPARADO de la Metodologia v2. v2 es de REVERSION (entra
contra el extremo del RSI); esto es SEGUIMIENTO de tendencia - reusa el
unico elemento validado de v2 (la vela de rechazo geometrica), pero con un
contexto de entrada opuesto: a favor de la tendencia, no contra ella.

Diseño pedido por el usuario (punto de partida):

1. Tendencia: EMA(50) en 1H. Alcista si el precio cierra por encima de la
   EMA de forma sostenida (`trend_confirmation_candles`, 5-8 velas,
   default 6); bajista si cierra por debajo. Se evalua sobre las velas
   ANTERIORES a la de rechazo (el pullback en si puede tocar/perforar la
   EMA con la mecha - es el punto del retroceso -, pero el contexto de
   tendencia previo tiene que estar limpio).
2. Retroceso hacia la EMA: la vela de rechazo tiene que tocar o acercarse
   a la EMA vigente (misma logica de proximidad que
   `StructuralPullbackStrategy._find_pullback_level`,
   `level_proximity_atr_mult` x ATR, default 0.5x).
3. Entrada solo con vela de rechazo geometrica (mismo test que v2:
   `is_hammer`/`is_shooting_star`, mecha >=1.5x el cuerpo, mecha opuesta
   <=30% del rango) A FAVOR de la tendencia - martillo solo en tendencia
   alcista, estrella fugaz solo en bajista. Igual que
   `RangeReversionStrategy`, NO se exige una vela de confirmacion
   separada (el diseño del usuario solo menciona la vela de rechazo como
   gatillo) - mismo punto de diseño discutible ya señalado en esa
   estrategia, dado el hallazgo de "Metodología v2 pura" (sacar la
   confirmacion degrada BTC). Entrada de mercado en la propia vela de
   rechazo.
4. SL detras del extremo de la vela de rechazo (mismo margen de ATR que
   usa v2, `sl_atr_margin_mult` x ATR). TP: "a definir por Code" - se
   reusa el mismo mecanismo de v2 (`nearest_level_beyond_price` sobre
   niveles manuales+fractales, con fallback a un multiplo de riesgo fijo
   si el nivel mas cercano da mala relacion riesgo/beneficio) en vez de
   inventar un esquema nuevo - ya esta validado y evita agregar un
   parametro mas sin justificacion.

No hereda de `StructuralPullbackStrategy` (la logica de entrada es
distinta de punta a punta: tendencia+pullback vs RSI extremo+nivel) pero
reusa las mismas piezas de infraestructura (`is_hammer`/`is_shooting_star`,
`get_levels_for_symbol`, `nearest_level_beyond_price`) - mismo patron que
`BreakoutStrategy`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.candles import is_hammer, is_shooting_star
from src.indicators import atr, ema
from src.levels import DEFAULT_LEVELS_PATH, get_levels_for_symbol, nearest_level_beyond_price
from src.strategy_base import Strategy
from src.types import Signal


@dataclass(frozen=True)
class _Setup:
    signal: Signal
    stop_loss: float
    take_profit: float


class TrendPullbackStrategy(Strategy):
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        *,
        levels_path: str | Path = DEFAULT_LEVELS_PATH,
        ema_period: int = 50,
        trend_confirmation_candles: int = 6,
        atr_period: int = 14,
        level_proximity_atr_mult: float = 0.5,
        rejection_wick_ratio: float = 1.5,
        sl_atr_margin_mult: float = 0.5,
        min_risk_reward: float = 1.5,
        fallback_rr_multiple: float = 2.0,
    ) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self.levels_path = levels_path
        self.ema_period = ema_period
        self.trend_confirmation_candles = trend_confirmation_candles
        self.atr_period = atr_period
        self.level_proximity_atr_mult = level_proximity_atr_mult
        self.rejection_wick_ratio = rejection_wick_ratio
        self.sl_atr_margin_mult = sl_atr_margin_mult
        self.min_risk_reward = min_risk_reward
        self.fallback_rr_multiple = fallback_rr_multiple
        self.min_history = 3 * max(ema_period, atr_period) + trend_confirmation_candles

        self._cached_time = None
        self._cached_setup: _Setup | None = None

    # -- Interfaz Strategy ---------------------------------------------------

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if len(data) < self.min_history:
            return Signal.HOLD
        setup = self._get_setup(data)
        return setup.signal if setup else Signal.HOLD

    def stop_loss_price(self, data: pd.DataFrame, signal: Signal) -> float:
        return self._require_setup(data, signal).stop_loss

    def take_profit_price(self, data: pd.DataFrame, signal: Signal) -> float:
        return self._require_setup(data, signal).take_profit

    def _require_setup(self, data: pd.DataFrame, signal: Signal) -> _Setup:
        setup = self._get_setup(data)
        if setup is None or setup.signal != signal:
            raise ValueError(
                "stop_loss_price/take_profit_price invocado sin un setup vigente "
                "para esta senal. Llamar siempre a generate_signal() primero, "
                "sobre el mismo DataFrame."
            )
        return setup

    def _get_setup(self, data: pd.DataFrame) -> _Setup | None:
        last_time = data["time"].iloc[-1]
        if self._cached_time == last_time:
            return self._cached_setup
        setup = self._analyze(data)
        self._cached_time = last_time
        self._cached_setup = setup
        return setup

    # -- Logica del setup -----------------------------------------------------

    def _analyze(self, data: pd.DataFrame) -> _Setup | None:
        idx = len(data) - 1
        trend_start = idx - self.trend_confirmation_candles
        if trend_start < 0:
            return None

        ema_series = ema(data["close"], period=self.ema_period)
        current_ema = ema_series.iloc[idx]
        trend_emas = ema_series.iloc[trend_start:idx]
        if pd.isna(current_ema) or trend_emas.isna().any():
            return None

        trend_closes = data["close"].iloc[trend_start:idx]
        uptrend = (trend_closes > trend_emas).all()
        downtrend = (trend_closes < trend_emas).all()
        if not uptrend and not downtrend:
            return None

        atr_series = atr(data, period=self.atr_period)
        current_atr = atr_series.iloc[idx]
        if pd.isna(current_atr) or current_atr <= 0:
            return None

        rejection = data.iloc[idx]
        proximity = self.level_proximity_atr_mult * current_atr
        entry_price = rejection["close"]
        levels = get_levels_for_symbol(self.symbol, data, manual_levels_path=self.levels_path)

        if uptrend:
            if not is_hammer(rejection, min_wick_to_body=self.rejection_wick_ratio):
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
        if abs(rejection["high"] - current_ema) > proximity:
            return None
        stop_loss = rejection["high"] + self.sl_atr_margin_mult * current_atr
        take_profit = self._calculate_take_profit(levels, entry_price, Signal.SELL, stop_loss)
        if take_profit < entry_price < stop_loss:
            return _Setup(signal=Signal.SELL, stop_loss=stop_loss, take_profit=take_profit)
        return None

    def _calculate_take_profit(
        self, levels: list[float], entry_price: float, direction: Signal, stop_loss: float
    ) -> float:
        risk_distance = abs(entry_price - stop_loss)
        fallback = (
            entry_price + self.fallback_rr_multiple * risk_distance
            if direction == Signal.BUY
            else entry_price - self.fallback_rr_multiple * risk_distance
        )
        level = nearest_level_beyond_price(
            levels, entry_price, direction="up" if direction == Signal.BUY else "down"
        )
        if level is None or risk_distance <= 0:
            return fallback
        reward_distance = abs(level - entry_price)
        if reward_distance / risk_distance < self.min_risk_reward:
            return fallback
        return level
