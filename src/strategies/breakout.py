"""Estrategia de ruptura de consolidacion (evaluada 23/09/2026, NO activa).

Sistema SEPARADO de la Metodologia v2 (`structural_pullback.py`, reversion
sobre nivel + RSI extremo) - no la reemplaza ni la modifica. Pedido del
usuario: operar la ruptura de un rango comprimido en vez de esperar un
pullback sobre un nivel. Traduce estos 4 puntos:

  1. Consolidacion: el ATR promedio de las ultimas `consolidation_short_window`
     velas (10-14 tipico) esta por debajo de su propio promedio de las
     ultimas `consolidation_long_window` velas (50) - volatilidad
     contrayendose respecto a su propia base reciente.
  2. Senal: la vela de ruptura cierra por fuera del rango (maximo/minimo de
     las velas de consolidacion, sin incluir la vela de ruptura) Y su
     volumen es >= `volume_breakout_mult` (1.5x) el promedio de volumen de
     las ultimas `volume_ma_period` velas (20).
  3. Confirmacion: la vela siguiente cierra tambien por fuera del rango roto
     (misma direccion, sin volver a meterse adentro - "sin invalidar el
     rango roto").
  4. SL en el borde opuesto del rango roto. TP a un multiplo de riesgo
     minimo (`min_risk_reward`, default 2:1) - a diferencia de la
     Metodologia v2, ac no hay nivel estructural "siguiente": el rango
     roto ya ES el nivel de referencia.

Igual que la Metodologia v2 (ver `structural_pullback.py`), si los datos no
traen columna de volumen (tick_volume/volume/real_volume - el caso de los
CSV de Twelve Data usados en el backtest) el chequeo de volumen no bloquea,
porque no hay forma de exigir algo que no esta en los datos - documentado
igual en CLAUDE.md para este backtest.

Bucket de capital separado (pedido explicito del usuario, no asumido): en
vivo, el dimensionamiento de esta estrategia NO usa el capital total de la
cuenta ni el 2% de riesgo de la Metodologia v2 - usa un bucket del 15% del
capital real, arriesgando 3% de ESE bucket por operacion (ver
`src/bot.py::iterate`, rama `isinstance(strategy, BreakoutStrategy)`).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.indicators import atr
from src.strategy_base import Strategy
from src.types import Signal

_VOLUME_COLUMNS = ("tick_volume", "volume", "real_volume")


@dataclass(frozen=True)
class _Setup:
    signal: Signal
    stop_loss: float
    take_profit: float


class BreakoutStrategy(Strategy):
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        *,
        atr_period: int = 14,
        consolidation_short_window: int = 14,
        consolidation_long_window: int = 50,
        volume_ma_period: int = 20,
        volume_breakout_mult: float = 1.5,
        min_risk_reward: float = 2.0,
    ) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self.atr_period = atr_period
        self.consolidation_short_window = consolidation_short_window
        self.consolidation_long_window = consolidation_long_window
        self.volume_ma_period = volume_ma_period
        self.volume_breakout_mult = volume_breakout_mult
        self.min_risk_reward = min_risk_reward
        self.min_history = atr_period + consolidation_long_window + 5

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
        confirmation_idx = len(data) - 1
        breakout_idx = confirmation_idx - 1
        range_start = breakout_idx - self.consolidation_short_window
        if range_start < self.consolidation_long_window:
            return None

        if not self._is_consolidating(data, breakout_idx):
            return None

        range_window = data.iloc[range_start:breakout_idx]
        range_high = range_window["high"].max()
        range_low = range_window["low"].min()
        if range_high <= range_low:
            return None

        breakout = data.iloc[breakout_idx]
        confirmation = data.iloc[confirmation_idx]
        volume_series = self._volume_series(data)

        for direction in (Signal.BUY, Signal.SELL):
            if not self._is_breakout_candle(breakout, direction, range_high, range_low):
                continue
            if not self._volume_confirmed(volume_series, breakout_idx):
                continue
            if not self._is_confirmation_candle(confirmation, direction, range_high, range_low):
                continue

            stop_loss = range_low if direction == Signal.BUY else range_high
            entry_price = confirmation["close"]
            risk_distance = abs(entry_price - stop_loss)
            if risk_distance <= 0:
                continue
            take_profit = (
                entry_price + self.min_risk_reward * risk_distance
                if direction == Signal.BUY
                else entry_price - self.min_risk_reward * risk_distance
            )
            return _Setup(signal=direction, stop_loss=stop_loss, take_profit=take_profit)

        return None

    def _is_consolidating(self, data: pd.DataFrame, breakout_idx: int) -> bool:
        # Comparamos el ATR promedio reciente contra su propio promedio de
        # base (50 velas), usando solo velas ANTERIORES a la de ruptura -
        # la ruptura en si misma no debe contar como parte de la
        # "compresion" que la precede.
        atr_series = atr(data.iloc[:breakout_idx], period=self.atr_period)
        if atr_series.isna().all():
            return False
        short_avg = atr_series.tail(self.consolidation_short_window).mean()
        long_avg = atr_series.tail(self.consolidation_long_window).mean()
        if pd.isna(short_avg) or pd.isna(long_avg):
            return False
        return short_avg < long_avg

    @staticmethod
    def _is_breakout_candle(candle: pd.Series, direction: Signal, range_high: float, range_low: float) -> bool:
        if direction == Signal.BUY:
            return candle["close"] > range_high
        return candle["close"] < range_low

    @staticmethod
    def _is_confirmation_candle(candle: pd.Series, direction: Signal, range_high: float, range_low: float) -> bool:
        # "Sin invalidar el rango roto": la vela siguiente tiene que seguir
        # cerrando del lado de afuera del rango, no necesariamente mas
        # lejos que la vela de ruptura.
        if direction == Signal.BUY:
            return candle["close"] > range_high
        return candle["close"] < range_low

    @staticmethod
    def _volume_series(data: pd.DataFrame) -> pd.Series | None:
        for column in _VOLUME_COLUMNS:
            if column in data.columns:
                return data[column].astype(float)
        return None

    def _volume_confirmed(self, volume_series: pd.Series | None, idx: int) -> bool:
        # Igual que en structural_pullback.py: si no hay columna de volumen
        # en los datos (backtests sobre CSV de Twelve Data), no se puede
        # exigir nada -> no bloquea. En vivo, MT5 siempre entrega tick_volume.
        if volume_series is None:
            return True
        volume_ma = volume_series.rolling(
            self.volume_ma_period, min_periods=max(2, self.volume_ma_period // 2)
        ).mean()
        ma_at_idx = volume_ma.iloc[idx]
        if pd.isna(ma_at_idx) or ma_at_idx <= 0:
            return True
        return volume_series.iloc[idx] >= self.volume_breakout_mult * ma_at_idx
