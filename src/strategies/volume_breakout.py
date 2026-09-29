"""Ruptura estructural con volumen, BTC (30/09/2026) - evaluacion puntual,
diseño NUEVO, distinto de `src/strategies/breakout.py` (la ruptura de
consolidacion evaluada el 23/09/2026, rechazada con PF 1.06-1.11) y del
"Breakout de continuidad BTC en 4H" (PF maximo 1.11, sin filtro de
volumen). No reemplaza ni toca ninguna de las dos - queda como una
tercera evaluacion sobre BTC despues de que la linea de tendencia-pullback
a EMA se agoto en tres intentos (EMA 50, EMA 21, EMA 50 + confirmacion,
todos rechazados el 29-30/09/2026).

Hipotesis del usuario: BTC no muestra retrocesos ordenados a una media
(por eso fallo tendencia-pullback), pero si tiene fases de consolidacion
seguidas de rupturas con impulso - patron tipico de un activo de alta
volatilidad. Diseño pedido, sin margen de interpretacion en los 4 puntos:

  1. Consolidacion: rango de precio (maximo-minimo) de las ultimas
     `consolidation_window` velas (N=8-12, candidato a elegir por
     backtest) contenido dentro de un ancho angosto respecto al ATR del
     periodo - `range_width_atr_mult` (fijo en 1.5x, NO se optimiza:
     agregar un tercer eje de busqueda ademas de N y el umbral de volumen
     multiplicaria las combinaciones y el riesgo de sobreajuste que el
     usuario pidio evitar explicitamente; 1.5x es un valor moderado,
     conservador respecto al 2.0x que usa `RangeReversionStrategy` para
     su ancho MINIMO de rango - aca es un ancho MAXIMO, direccion
     opuesta).
  2. Ruptura: la vela SIGUIENTE a la ventana de consolidacion cierra por
     fuera del rango (arriba o abajo) - "con cuerpo real, no mecha":
     ademas de cerrar afuera, el cuerpo de la vela (|close-open|) tiene
     que ser la parte dominante de su rango total (`min_body_ratio`,
     fijo en 0.5 - mismo criterio de no-optimizacion que el punto
     anterior). Entrada de mercado en esa misma vela (el diseño pedido no
     menciona una vela de confirmacion separada, a diferencia de la
     ruptura de consolidacion del 23/09 que si la exigia).
  3. Confirmacion de volumen: volumen de la vela de ruptura >=
     `volume_breakout_mult` el promedio de las ultimas `volume_ma_period`
     velas (20) - CANDIDATO A OPTIMIZAR (1.3x/1.5x/2.0x), unico eje de
     busqueda ademas de N, protocolo de seleccion fuera de muestra en
     `scripts/backtest_volume_breakout.py` (barrido sobre la 1ra mitad
     cronologica, validacion en la 2da - mismo patron que
     `scripts/backtest_regime_filter.py`). Igual que en v2/BreakoutStrategy,
     si los datos no traen columna de volumen el chequeo no bloquea (no se
     puede exigir algo que no esta en los datos) - a diferencia de esos
     dos casos, aca la evaluacion en BTC espera un CSV con volumen real
     (export de MT5), no el CSV de Twelve Data sin volumen que usa el
     resto del proyecto - ver CLAUDE.md para la aclaracion completa.
  4. SL detras del extremo opuesto del rango de consolidacion (con un
     margen chico de ATR, `sl_atr_margin_mult`, mismo patron que el resto
     de las estrategias de este proyecto). TP: "a definir por Code" - se
     reusa el mismo mecanismo ya validado de v2/v3 (nivel estructural mas
     cercano con fallback a un multiplo de riesgo fijo si da mala
     relacion riesgo/beneficio), no se inventa un esquema nuevo.

No hereda de ninguna estrategia existente (logica de punta a punta
distinta) pero reusa `get_levels_for_symbol`/`nearest_level_beyond_price`
para el TP - mismo patron que `TrendPullbackStrategy`/`BreakoutStrategy`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.indicators import atr
from src.levels import DEFAULT_LEVELS_PATH, get_levels_for_symbol, nearest_level_beyond_price
from src.strategy_base import Strategy
from src.types import Signal

_VOLUME_COLUMNS = ("tick_volume", "volume", "real_volume")


@dataclass(frozen=True)
class _Setup:
    signal: Signal
    stop_loss: float
    take_profit: float


class VolumeBreakoutStrategy(Strategy):
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        *,
        levels_path: str | Path = DEFAULT_LEVELS_PATH,
        consolidation_window: int = 10,
        range_width_atr_mult: float = 1.5,
        atr_period: int = 14,
        min_body_ratio: float = 0.5,
        volume_ma_period: int = 20,
        volume_breakout_mult: float = 1.5,
        sl_atr_margin_mult: float = 0.3,
        min_risk_reward: float = 1.5,
        fallback_rr_multiple: float = 2.0,
    ) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self.levels_path = levels_path
        self.consolidation_window = consolidation_window
        self.range_width_atr_mult = range_width_atr_mult
        self.atr_period = atr_period
        self.min_body_ratio = min_body_ratio
        self.volume_ma_period = volume_ma_period
        self.volume_breakout_mult = volume_breakout_mult
        self.sl_atr_margin_mult = sl_atr_margin_mult
        self.min_risk_reward = min_risk_reward
        self.fallback_rr_multiple = fallback_rr_multiple
        self.min_history = atr_period + consolidation_window + volume_ma_period + 5

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
        breakout_idx = len(data) - 1
        range_start = breakout_idx - self.consolidation_window
        if range_start < 0:
            return None

        range_window = data.iloc[range_start:breakout_idx]
        range_high = range_window["high"].max()
        range_low = range_window["low"].min()
        if range_high <= range_low:
            return None

        atr_series = atr(data.iloc[:breakout_idx], period=self.atr_period)
        current_atr = atr_series.iloc[-1] if len(atr_series) else float("nan")
        if pd.isna(current_atr) or current_atr <= 0:
            return None

        if (range_high - range_low) > self.range_width_atr_mult * current_atr:
            return None

        breakout = data.iloc[breakout_idx]
        total_candle_range = breakout["high"] - breakout["low"]
        body = abs(breakout["close"] - breakout["open"])
        if total_candle_range <= 0 or body < self.min_body_ratio * total_candle_range:
            return None

        volume_series = self._volume_series(data)
        if not self._volume_confirmed(volume_series, breakout_idx):
            return None

        levels = get_levels_for_symbol(self.symbol, data, manual_levels_path=self.levels_path)
        entry_price = breakout["close"]

        if entry_price > range_high:
            direction = Signal.BUY
            stop_loss = range_low - self.sl_atr_margin_mult * current_atr
        elif entry_price < range_low:
            direction = Signal.SELL
            stop_loss = range_high + self.sl_atr_margin_mult * current_atr
        else:
            return None

        take_profit = self._calculate_take_profit(levels, entry_price, direction, stop_loss)
        if direction == Signal.BUY and not (stop_loss < entry_price < take_profit):
            return None
        if direction == Signal.SELL and not (take_profit < entry_price < stop_loss):
            return None
        return _Setup(signal=direction, stop_loss=stop_loss, take_profit=take_profit)

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

    @staticmethod
    def _volume_series(data: pd.DataFrame) -> pd.Series | None:
        for column in _VOLUME_COLUMNS:
            if column in data.columns:
                return data[column].astype(float)
        return None

    def _volume_confirmed(self, volume_series: pd.Series | None, idx: int) -> bool:
        if volume_series is None:
            return True
        volume_ma = volume_series.rolling(
            self.volume_ma_period, min_periods=max(2, self.volume_ma_period // 2)
        ).mean()
        ma_at_idx = volume_ma.iloc[idx]
        if pd.isna(ma_at_idx) or ma_at_idx <= 0:
            return True
        return volume_series.iloc[idx] >= self.volume_breakout_mult * ma_at_idx
