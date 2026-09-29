"""Metodologia de rango para Oro (28/09/2026) - evaluacion de una hipotesis
GRANDE, sistema SEPARADO de la Metodologia v2, pensado para correr en
PARALELO a ella y cubrir el tiempo donde hoy no se opera nada porque el
RSI no llega a un extremo real (35/65).

Pedido explicito del usuario, con diseño propio (no interpretacion mia):

  1. Deteccion de regimen: ADX(14) por debajo de un umbral (`adx_threshold`,
     20.0 default) sostenido durante `regime_confirmation_candles` (8-10)
     velas consecutivas en 1H - confirmacion de mercado sin tendencia.
     Elegido ADX sobre la alternativa de ancho de Bollinger porque ya
     existe `true_range`/el patron de suavizado de Wilder en
     `src/indicators.py` (mismo que usan `rsi`/`atr`) - se integra sin
     introducir un segundo criterio de "percentil de historial reciente"
     que Bollinger hubiera requerido.
  2. Entrada (solo si el regimen de arriba confirma rango): comprar cerca
     del piso tecnico del rango cuando el RSI(14) real toque 40 (no 35,
     el usuario aclaro que en rango angosto rara vez llega a extremos
     reales) + vela de rechazo con el mismo test geometrico estricto que
     `StructuralPullbackStrategy` (mecha >=1.5x el cuerpo, mecha opuesta
     <=30% del rango, via `is_hammer`/`is_shooting_star`). Espejo para
     venta cerca del techo con RSI en 60.
  3. Salida: TP en el punto medio del rango (mas conservador que el
     extremo opuesto, tal como pidio el usuario para el primer test). SL
     apenas afuera del piso/techo (margen de ATR chico, angosto por
     diseño).

Decisiones de implementacion tomadas sin instruccion explicita del
usuario (marcadas como tal, ajustables):

  - El "rango" se define con las MISMAS `regime_confirmation_candles`
    velas que confirman el regimen (piso = minimo de los lows, techo =
    maximo de los highs de esa ventana) - evita introducir un segundo
    parametro de "ventana de rango" separado del de deteccion de regimen.
  - "Cerca del piso/techo" usa la misma logica de proximidad que
    `StructuralPullbackStrategy._find_pullback_level`
    (`level_proximity_atr_mult * ATR`, default 0.5x).
  - A diferencia de la Metodologia v2, NO se exige una vela de
    confirmacion separada despues de la de rechazo - el diseño del
    usuario solo menciona la vela de rechazo como gatillo. Esto es una
    diferencia deliberada respecto a v2 (que si la exige, y el backtest
    del 28/09/2026 mostro que sacarla degrada BTC) - se deja documentada
    esta decision explicitamente porque es el punto de diseño mas
    discutible de esta estrategia; si el resultado sale ruidoso, sumar
    una vela de confirmacion es el primer ajuste natural a probar.
  - Sin "giro confirmado" de RSI (a diferencia de v2): el diseño pedido
    es mas simple (solo "RSI toca 40/60"), consistente con que en un
    rango angosto el RSI oscila mucho mas seguido que en una reversion de
    tendencia.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.candles import is_hammer, is_shooting_star
from src.indicators import adx, atr, rsi
from src.strategy_base import Strategy
from src.types import Signal


@dataclass(frozen=True)
class _Setup:
    signal: Signal
    stop_loss: float
    take_profit: float


class RangeReversionStrategy(Strategy):
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        *,
        adx_period: int = 14,
        adx_threshold: float = 20.0,
        regime_confirmation_candles: int = 8,
        atr_period: int = 14,
        rsi_period: int = 14,
        rsi_buy_level: float = 40.0,
        rsi_sell_level: float = 60.0,
        rejection_wick_ratio: float = 1.5,
        level_proximity_atr_mult: float = 0.5,
        sl_atr_margin_mult: float = 0.5,
    ) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.regime_confirmation_candles = regime_confirmation_candles
        self.atr_period = atr_period
        self.rsi_period = rsi_period
        self.rsi_buy_level = rsi_buy_level
        self.rsi_sell_level = rsi_sell_level
        self.rejection_wick_ratio = rejection_wick_ratio
        self.level_proximity_atr_mult = level_proximity_atr_mult
        self.sl_atr_margin_mult = sl_atr_margin_mult
        self.min_history = 3 * max(adx_period, rsi_period, atr_period) + regime_confirmation_candles

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
        window_start = idx - self.regime_confirmation_candles + 1
        if window_start < 0:
            return None

        adx_series = adx(data, period=self.adx_period)
        regime_window = adx_series.iloc[window_start : idx + 1]
        if regime_window.isna().any() or not (regime_window < self.adx_threshold).all():
            return None  # no confirma regimen de rango

        atr_series = atr(data, period=self.atr_period)
        current_atr = atr_series.iloc[idx]
        if pd.isna(current_atr) or current_atr <= 0:
            return None

        range_window = data.iloc[window_start : idx + 1]
        range_floor = range_window["low"].min()
        range_ceiling = range_window["high"].max()
        if range_ceiling <= range_floor:
            return None

        rsi_series = rsi(data["close"], period=self.rsi_period)
        current_rsi = rsi_series.iloc[idx]
        if pd.isna(current_rsi):
            return None

        rejection = data.iloc[idx]
        proximity = self.level_proximity_atr_mult * current_atr
        entry_price = rejection["close"]

        if (
            current_rsi <= self.rsi_buy_level
            and is_hammer(rejection, min_wick_to_body=self.rejection_wick_ratio)
            and abs(rejection["low"] - range_floor) <= proximity
        ):
            stop_loss = range_floor - self.sl_atr_margin_mult * current_atr
            take_profit = (range_floor + range_ceiling) / 2
            if stop_loss < entry_price < take_profit:
                return _Setup(signal=Signal.BUY, stop_loss=stop_loss, take_profit=take_profit)

        if (
            current_rsi >= self.rsi_sell_level
            and is_shooting_star(rejection, min_wick_to_body=self.rejection_wick_ratio)
            and abs(rejection["high"] - range_ceiling) <= proximity
        ):
            stop_loss = range_ceiling + self.sl_atr_margin_mult * current_atr
            take_profit = (range_floor + range_ceiling) / 2
            if take_profit < entry_price < stop_loss:
                return _Setup(signal=Signal.SELL, stop_loss=stop_loss, take_profit=take_profit)

        return None
