"""Ruptura de nivel estructural con volumen, BTC (29/09/2026) - cuarta
evaluacion sobre BTC despues de que tendencia-pullback a EMA se agoto en
tres intentos (EMA 50, EMA 21, EMA 50 + confirmacion, los tres rechazados
el 29-30/09/2026) y de que la ruptura de CONSOLIDACION con volumen
(`volume_breakout.py`, el mismo dia) quedara sin muestra suficiente (0-7
señales crudas segun N/umbral).

Diseño DISTINTO del de `volume_breakout.py`: en vez de detectar un rango
de consolidacion calculado sobre el ATR, esta version ancla la ruptura a
un **nivel estructural real** - la misma fuente que usan v2
(`structural_pullback.py`) y v3 (`trend_pullback.py`): manuales
(`config/levels.json`) union fractales automaticos, via
`get_levels_for_symbol`/`nearest_level_beyond_price`. La hipotesis es que
anclar a un nivel conocido en vez de a una ventana de rango arbitraria
deja pasar mas candidatos (el filtro de volumen, no la geometria, fue el
verdadero cuello de botella del intento anterior).

Diseño (confirmado con el usuario el 29/09/2026, incluyendo el punto de
la vela de confirmacion - ver CLAUDE.md):

  1. Nivel: el nivel estructural mas cercano por encima (para un quiebre
     alcista) o por debajo (bajista) del cierre de la vela PREVIA a la de
     ruptura - "el nivel que el precio esta por romper", no cualquier
     nivel lejano que tecnicamente siga del otro lado. Los niveles se
     calculan con datos ANTERIORES a la vela de ruptura (sin lookahead).
  2. Ruptura: la vela de ruptura cierra por fuera del nivel, con cuerpo
     real dominante (`min_body_ratio`, no una mecha) - mismo criterio ya
     usado en `breakout.py`/`volume_breakout.py`.
  3. Volumen: volumen de la vela de ruptura >= `volume_breakout_mult` el
     promedio de las ultimas `volume_ma_period` velas - CANDIDATO A
     OPTIMIZAR (1.3x/1.5x/2.0x), unico eje de busqueda, mismo protocolo de
     seleccion fuera de muestra que `volume_breakout.py`
     (`scripts/backtest_level_breakout.py`). Si los datos no traen columna
     de volumen, el chequeo no bloquea (no se puede exigir algo que no
     esta en los datos).
  4. Confirmacion: a diferencia de `volume_breakout.py` (que entraba en la
     propia vela de ruptura), aca SI se exige una vela de confirmacion
     separada - la vela SIGUIENTE tiene que cerrar tambien del lado
     roto del nivel, sin volver a meterse adentro (mismo criterio que
     `BreakoutStrategy._is_confirmation_candle` y que v2). Decision
     explicita del usuario, no asumida: dado que sacar la confirmacion ya
     fallo en 3 intentos de v3 en BTC y en la ruptura de consolidacion de
     septiembre, se prefiere la variante mas conservadora aunque reduzca
     la muestra.
  5. Entrada de mercado en el cierre de la vela de confirmacion. SL detras
     del nivel roto (+ margen chico de ATR, mismo patron del resto del
     proyecto). TP: mecanismo ya validado de v2/v3 - proximo nivel
     estructural mas alla de la entrada, con fallback a un multiplo de
     riesgo fijo si ese nivel da mala relacion riesgo/beneficio.

No hereda de ninguna estrategia existente (logica de punta a punta propia)
pero reusa `get_levels_for_symbol`/`nearest_level_beyond_price` tanto para
detectar el nivel roto como para el TP - mismo patron que
`TrendPullbackStrategy`/`VolumeBreakoutStrategy`.
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


class LevelBreakoutStrategy(Strategy):
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        *,
        levels_path: str | Path = DEFAULT_LEVELS_PATH,
        atr_period: int = 14,
        min_body_ratio: float = 0.5,
        volume_ma_period: int = 20,
        volume_breakout_mult: float = 1.5,
        sl_atr_margin_mult: float = 0.3,
        min_risk_reward: float = 1.5,
        fallback_rr_multiple: float = 2.0,
        fractal_lookback: int = 200,
    ) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self.levels_path = levels_path
        self.atr_period = atr_period
        self.min_body_ratio = min_body_ratio
        self.volume_ma_period = volume_ma_period
        self.volume_breakout_mult = volume_breakout_mult
        self.sl_atr_margin_mult = sl_atr_margin_mult
        self.min_risk_reward = min_risk_reward
        self.fallback_rr_multiple = fallback_rr_multiple
        self.fractal_lookback = fractal_lookback
        self.min_history = max(atr_period, volume_ma_period) + fractal_lookback + 5

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
        if breakout_idx < 1:
            return None

        pre_breakout = data.iloc[:breakout_idx]
        levels_before = self._levels(pre_breakout)
        reference_price = data["close"].iloc[breakout_idx - 1]

        atr_series = atr(pre_breakout, period=self.atr_period)
        current_atr = atr_series.iloc[-1] if len(atr_series) else float("nan")
        if pd.isna(current_atr) or current_atr <= 0:
            return None

        breakout = data.iloc[breakout_idx]
        confirmation = data.iloc[confirmation_idx]
        volume_series = self._volume_series(data)

        for direction in (Signal.BUY, Signal.SELL):
            level = nearest_level_beyond_price(
                levels_before, reference_price, direction="up" if direction == Signal.BUY else "down"
            )
            if level is None:
                continue
            if not self._is_breakout_candle(breakout, direction, level):
                continue
            if not self._volume_confirmed(volume_series, breakout_idx):
                continue
            if not self._is_confirmation_candle(confirmation, direction, level):
                continue

            stop_loss = (
                level - self.sl_atr_margin_mult * current_atr
                if direction == Signal.BUY
                else level + self.sl_atr_margin_mult * current_atr
            )
            entry_price = confirmation["close"]
            risk_distance = abs(entry_price - stop_loss)
            if risk_distance <= 0:
                continue

            levels_at_entry = self._levels(data.iloc[: confirmation_idx + 1])
            take_profit = self._calculate_take_profit(levels_at_entry, entry_price, direction, stop_loss)
            if direction == Signal.BUY and not (stop_loss < entry_price < take_profit):
                continue
            if direction == Signal.SELL and not (take_profit < entry_price < stop_loss):
                continue
            return _Setup(signal=direction, stop_loss=stop_loss, take_profit=take_profit)

        return None

    def _levels(self, data: pd.DataFrame) -> list[float]:
        return get_levels_for_symbol(self.symbol, data, manual_levels_path=self.levels_path)

    def _is_breakout_candle(self, candle: pd.Series, direction: Signal, level: float) -> bool:
        total_range = candle["high"] - candle["low"]
        body = abs(candle["close"] - candle["open"])
        if total_range <= 0 or body < self.min_body_ratio * total_range:
            return False
        if direction == Signal.BUY:
            return candle["close"] > level
        return candle["close"] < level

    @staticmethod
    def _is_confirmation_candle(candle: pd.Series, direction: Signal, level: float) -> bool:
        # "Sin invalidar la ruptura": la vela siguiente sigue cerrando del
        # lado de afuera del nivel roto, sin exigir que avance mas todavia.
        if direction == Signal.BUY:
            return candle["close"] > level
        return candle["close"] < level

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
