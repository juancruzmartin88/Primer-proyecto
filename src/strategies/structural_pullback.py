"""Estrategia estructural con pullback (seccion 10 del sistema, version 2).

Traduce a codigo el pseudocodigo "resumen ejecutable para el bot":

  1. Detectar ruptura/rebote reciente desde un nivel estructural.
  2. NO entrar en la vela de impulso.
  3. Esperar el pullback de vuelta hacia el nivel.
  4. Exigir vela de rechazo (martillo / estrella fugaz segun direccion)
     seguida de una vela de confirmacion que cierre a favor de la operacion.
  5. Exigir que el RSI(14) cruce el nivel 50 en la direccion de la operacion
     entre esas dos velas.
  6. SL segun ATR(10-14) o el extremo real del pullback (el que sea mas
     conservador), con margen.
  7. TP en el siguiente nivel estructural relevante (o un multiplo de
     riesgo si no hay nivel util mas adelante).

Simplificaciones deliberadas respecto al proceso manual (documentadas para
que se puedan ajustar con el backtest, no son "gratis"):

  - "Ruptura o rebote reciente" se aproxima como: el nivel estuvo dentro
    de la distancia de proximidad (en ATR) de alguna vela en la ventana
    de `lookback_candles` anteriores a la vela de rechazo, Y la vela de
    rechazo vuelve a testear ese mismo nivel. No se distingue formalmente
    entre "ruptura" y "rebote" (ver seccion 5.4/10 del documento).
  - El bot solo evalua velas ya cerradas, nunca la vela en formacion. Por
    construccion, esto hace que la unica orden que emite sea de tipo
    Market (la vela de confirmacion ya cerro) - la variante con ordenes
    Limit sobre el pullback en formacion (seccion 6) no esta implementada
    en este loop automatico.
  - No hay filtro de tendencia mayor en 4H (se decidio arrancar sin el y
    sumarlo despues de validar el sistema base).
  - Los niveles se toman de `src/levels.py`: manuales primero
    (config/levels.json), fractales automaticos como respaldo.

Ajuste del 10/09/2026 (para subir la frecuencia de señales, muy baja en la
verificacion contra el registro real de operaciones): se saco el requisito
de que la vela de confirmacion cierre mas alla del extremo de la vela de
rechazo. Ese requisito no esta en el texto de la seccion 5 (que solo pide
"cierre a favor de la direccion esperada") y era redundante con el cruce
de RSI - de los cinco filtros del setup, era el que menos aportaba criterio
propio. El resto (nivel relevante, geometria de la vela de rechazo, cruce
de RSI, relacion riesgo/beneficio del TP) se mantiene sin cambios.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.candles import is_hammer, is_shooting_star
from src.indicators import atr, rsi
from src.levels import DEFAULT_LEVELS_PATH, get_levels_for_symbol, nearest_level_beyond_price
from src.strategy_base import Strategy
from src.types import Signal


@dataclass(frozen=True)
class _Setup:
    signal: Signal
    stop_loss: float
    take_profit: float


class StructuralPullbackStrategy(Strategy):
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        *,
        levels_path: str | Path = DEFAULT_LEVELS_PATH,
        lookback_candles: int = 8,
        level_proximity_atr_mult: float = 0.5,
        atr_period: int = 14,
        rsi_period: int = 14,
        sl_atr_margin_mult: float = 0.5,
        min_risk_reward: float = 1.5,
        fallback_rr_multiple: float = 2.0,
    ) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self.levels_path = levels_path
        self.lookback_candles = lookback_candles
        self.level_proximity_atr_mult = level_proximity_atr_mult
        self.atr_period = atr_period
        self.rsi_period = rsi_period
        self.sl_atr_margin_mult = sl_atr_margin_mult
        self.min_risk_reward = min_risk_reward
        self.fallback_rr_multiple = fallback_rr_multiple
        self.min_history = max(atr_period, rsi_period) + lookback_candles + 5

        self._cached_time = None
        self._cached_setup: _Setup | None = None

    # -- Interfaz Strategy ---------------------------------------------------

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if len(data) < self.min_history:
            return Signal.HOLD
        setup = self._get_setup(data)
        return setup.signal if setup else Signal.HOLD

    def stop_loss_price(self, data: pd.DataFrame, signal: Signal) -> float:
        setup = self._require_setup(data, signal)
        return setup.stop_loss

    def take_profit_price(self, data: pd.DataFrame, signal: Signal) -> float:
        setup = self._require_setup(data, signal)
        return setup.take_profit

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
        levels = get_levels_for_symbol(self.symbol, data, manual_levels_path=self.levels_path)
        if not levels:
            return None

        atr_series = atr(data, period=self.atr_period)
        current_atr = atr_series.iloc[-1]
        if pd.isna(current_atr) or current_atr <= 0:
            return None

        rsi_series = rsi(data["close"], period=self.rsi_period)

        confirmation_idx = len(data) - 1
        rejection_idx = confirmation_idx - 1
        if rejection_idx < 1:
            return None

        confirmation = data.iloc[confirmation_idx]
        rejection = data.iloc[rejection_idx]

        rsi_prev = rsi_series.iloc[rejection_idx]
        rsi_curr = rsi_series.iloc[confirmation_idx]
        if pd.isna(rsi_prev) or pd.isna(rsi_curr):
            return None

        for direction in (Signal.BUY, Signal.SELL):
            if not self._is_confirmation_candle(confirmation, direction):
                continue
            if not self._is_rejection_candle(rejection, direction):
                continue
            if not self._rsi_crossed_50(rsi_prev, rsi_curr, direction):
                continue

            level = self._find_pullback_level(data, levels, rejection_idx, direction, current_atr)
            if level is None:
                continue

            pullback_window = data.iloc[max(0, rejection_idx - self.lookback_candles) : confirmation_idx + 1]
            stop_loss = self._calculate_stop_loss(pullback_window, rejection, direction, current_atr)
            entry_price = confirmation["close"]
            take_profit = self._calculate_take_profit(levels, entry_price, direction, stop_loss)

            return _Setup(signal=direction, stop_loss=stop_loss, take_profit=take_profit)

        return None

    @staticmethod
    def _is_rejection_candle(candle: pd.Series, direction: Signal) -> bool:
        # Martillo para pullback alcista, estrella fugaz para pullback bajista
        # (seccion 3.4 y 5, version 2: "vela de rechazo tipo martillo/estrella
        # fugaz segun direccion").
        return is_hammer(candle) if direction == Signal.BUY else is_shooting_star(candle)

    @staticmethod
    def _is_confirmation_candle(candle: pd.Series, direction: Signal) -> bool:
        # Textual del sistema (seccion 5, v2): "vela que confirme la reversion
        # (cierre a favor de la direccion esperada)" - nada mas estricto que
        # esto. Antes se exigia ademas que cerrara mas alla del extremo de la
        # vela de rechazo; se saco (10/09/2026) por ser mas estricto que la
        # regla documentada y redundante con el cruce de RSI (las dos velan
        # por lo mismo: que el momentum ya giro).
        return candle["close"] > candle["open"] if direction == Signal.BUY else candle["close"] < candle["open"]

    @staticmethod
    def _rsi_crossed_50(rsi_prev: float, rsi_curr: float, direction: Signal) -> bool:
        if direction == Signal.BUY:
            return rsi_prev <= 50 and rsi_curr > 50
        return rsi_prev >= 50 and rsi_curr < 50

    def _find_pullback_level(
        self,
        data: pd.DataFrame,
        levels: list[float],
        rejection_idx: int,
        direction: Signal,
        current_atr: float,
    ) -> float | None:
        proximity = self.level_proximity_atr_mult * current_atr
        rejection = data.iloc[rejection_idx]
        rejection_price = rejection["low"] if direction == Signal.BUY else rejection["high"]

        search_start = max(0, rejection_idx - self.lookback_candles)
        prior_window = data.iloc[search_start:rejection_idx]
        if prior_window.empty:
            return None

        candidates = []
        for level in levels:
            if abs(rejection_price - level) > proximity:
                continue
            level_recently_in_play = (
                (prior_window["high"] - level).abs().le(proximity)
                | (prior_window["low"] - level).abs().le(proximity)
            ).any()
            if level_recently_in_play:
                candidates.append(level)

        if not candidates:
            return None
        return min(candidates, key=lambda lvl: abs(rejection_price - lvl))

    def _calculate_stop_loss(
        self, pullback_window: pd.DataFrame, rejection: pd.Series, direction: Signal, current_atr: float
    ) -> float:
        margin = self.sl_atr_margin_mult * current_atr
        if direction == Signal.BUY:
            extreme = min(pullback_window["low"].min(), rejection["low"])
            return extreme - margin
        extreme = max(pullback_window["high"].max(), rejection["high"])
        return extreme + margin

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
            # El nivel mas cercano da una relacion riesgo/beneficio pobre:
            # mejor un TP por multiplo de riesgo que un TP tecnicamente
            # "correcto" pero que no justifica el trade.
            return fallback
        return level
