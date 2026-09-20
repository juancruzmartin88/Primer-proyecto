"""Estrategia de entrada — Metodologia v2 (cuenta real, BTC + Oro, 14/09/2026).

Reemplaza el enfoque anterior (v1, "entrar en la vela de ruptura", con cruce
de RSI(14) simplemente por el nivel 50) por la metodologia documentada en la
seccion 4 del sistema de trading vigente. Confirmada con las dos primeras
operaciones reales que la aplicaron completa: BTC +$11.00 (11/09/2026) y
Oro +$134.07 (14/09/2026), ambas con Take Profit.

Traduce a codigo estos 4 requisitos, que tienen que cumplirse los 4 a la vez
(seccion 4.1: "el analisis combina 4 elementos siempre: estructura de precio,
volumen, RSI, patrones de velas japonesas"):

  1. Nivel tecnico relevante tocado (estructura de precio) - igual que v1:
     `src/levels.py`, manuales primero (config/levels.json), fractales como
     respaldo.
  2. Extremo de RSI real: el RSI(14) tuvo que haber cruzado por debajo de 35
     (sobreventa) o por encima de 65 (sobrecompra) en algun momento reciente
     - no cualquier cruce por 50 como en v1. (Umbral ajustado el 20/09/2026,
     ver mas abajo - originalmente 30/70.)
  3. Giro confirmado del RSI: no alcanza con tocar el extremo, el RSI ya
     tiene que haber vuelto a cruzar el umbral (30/70) para el momento de la
     vela de confirmacion. En los casos reales el giro ocurre varias velas
     antes de la entrada (ej. "RSI ~21, recuperacion sostenida con RSI en
     50s" en la operacion de Oro del 14/09) - por eso el cruce se busca en
     una ventana (`extreme_lookback`), no exigiendolo en la vela de rechazo
     misma.
  4. Vela de rechazo (martillo/estrella fugaz, igual que v1) + vela de
     confirmacion que cierre a favor - el mismo par de velas adyacentes de
     v1, pero ahora ademas se le exige volumen por encima del promedio
     reciente en la vela de rechazo (proxy de "volumen fuerte confirmado"
     mencionado en el historial real). Si los datos no traen columna de
     volumen (tick_volume/volume/real_volume - tipico en backtests con CSV
     de Twelve Data, que no la incluyen), este chequeo no bloquea: no hay
     forma de exigir algo que no esta en los datos. El bot en vivo si recibe
     `tick_volume` de MT5 en cada vela, asi que en produccion el chequeo
     queda activo.

Decisiones de arquitectura tomadas el 14/09/2026 (con el usuario, antes de
tocar cuenta real - ver conversacion o CLAUDE.md):

  - Se sigue mandando orden de MERCADO en la vela de confirmacion ya cerrada,
    no Buy Stop/Sell Stop pendiente. El bot solo actua sobre velas cerradas,
    asi que en la practica ya entra "despues" de que el rebote arranco -
    similar en espiritu a un Stop, sin agregar la complejidad operacional
    (colocar/vigilar/cancelar ordenes pendientes) de hacerlo literal.
  - Riesgo por operacion: 2% fijo (antes 1.5%), igual para BTC y Oro. Con
    $650 de capital esto reproduce el limite de 13 puntos de SL para Oro
    del ejemplo de la seccion 3.2 del sistema. Ese limite NO esta
    hardcodeado aca: surge solo de `RiskManager.calculate_position_size` +
    `enforce_min_lot_policy`, que en cuenta real bloquea cualquier señal
    cuyo SL tecnico, al lote minimo del broker, fuerce mas del 2% de riesgo
    real - se recalcula solo si cambia el capital, tal como pide la
    seccion 3 ("recalcular si el capital cambia").

SL/TP: sin cambios respecto a v1. El SL se calibra al ATR(14) de las
ultimas velas o al extremo real del pullback (el que sea mas conservador),
tal como pide la seccion 5 del sistema. El TP va al siguiente nivel
estructural, o a un multiplo de riesgo si ese nivel da mala relacion
riesgo/beneficio.

Ajuste del 20/09/2026 (validado con backtest antes de aplicarlo, a pedido
del usuario - "¿el doble filtro de RSI extremo + vela de rechazo es
demasiado estricto?"): `rsi_oversold`/`rsi_overbought` bajan de 30/70 a
35/65. Se probaron 4 variantes sobre los mismos 7 meses de BTC/Oro
($654.77, riesgo 2%, bloqueo de riesgo real activo):

  - Solo relajar RSI a 35/65 (manteniendo la vela de rechazo exigida):
    en BTC, PF 1.73->1.88, win rate 44.4%->47.5%, PnL $194->$415, drawdown
    practicamente igual (6.8%->7.6%). Confirmado con un split del periodo
    en dos mitades independientes (ambas mejoran en win rate y PnL; el PF
    empata en la primera mitad y mejora en la segunda) - no parece ruido
    de una racha puntual.
  - Sacar la vela de rechazo (con RSI en 30/70 o en 35/65): en ambos casos
    empeora fuerte - drawdown sube a 23-31% (vs 6-8% con la vela exigida)
    y el profit factor cae a ~1.0-1.1. La vela de rechazo esta haciendo un
    filtrado real (evita entrar varias veces sobre el mismo movimiento sin
    esperar un giro limpio) - se mantiene sin cambios.

En Oro la muestra fue demasiado chica en las 4 variantes (0-8 operaciones)
para sacar conclusiones - el cuello de botella ahi sigue siendo el capital
(seccion 3.2), no el criterio de entrada.
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

_VOLUME_COLUMNS = ("tick_volume", "volume", "real_volume")


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
        rejection_wick_ratio: float = 1.5,
        rsi_oversold: float = 35.0,
        rsi_overbought: float = 65.0,
        extreme_lookback: int = 10,
        volume_ma_period: int = 20,
        volume_confirmation_mult: float = 1.0,
    ) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self.levels_path = levels_path
        self.lookback_candles = lookback_candles
        self.level_proximity_atr_mult = level_proximity_atr_mult
        self.rejection_wick_ratio = rejection_wick_ratio
        self.atr_period = atr_period
        self.rsi_period = rsi_period
        self.sl_atr_margin_mult = sl_atr_margin_mult
        self.min_risk_reward = min_risk_reward
        self.fallback_rr_multiple = fallback_rr_multiple
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.extreme_lookback = extreme_lookback
        self.volume_ma_period = volume_ma_period
        self.volume_confirmation_mult = volume_confirmation_mult
        self.min_history = (
            max(atr_period, rsi_period, extreme_lookback) + lookback_candles + 5
        )

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
        volume_series = self._volume_series(data)

        confirmation_idx = len(data) - 1
        rejection_idx = confirmation_idx - 1
        if rejection_idx < 1:
            return None

        confirmation = data.iloc[confirmation_idx]
        rejection = data.iloc[rejection_idx]

        rsi_confirmation = rsi_series.iloc[confirmation_idx]
        if pd.isna(rsi_confirmation):
            return None

        for direction in (Signal.BUY, Signal.SELL):
            if not self._is_confirmation_candle(confirmation, direction):
                continue
            if not self._is_rejection_candle(rejection, direction):
                continue
            if not self._rsi_extreme_and_turn(rsi_series, rejection_idx, confirmation_idx, direction):
                continue
            if not self._volume_confirmed(volume_series, rejection_idx):
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

    def _is_rejection_candle(self, candle: pd.Series, direction: Signal) -> bool:
        # Martillo para reversion alcista, estrella fugaz para reversion
        # bajista (seccion 4, punto 4: "vela de rechazo... mecha en la
        # direccion contraria al movimiento previo, con cierre recuperando
        # parte del rango"). Ratio mecha/cuerpo configurable (1.5x default,
        # ver v1 para el porque de ese valor en vez del 2.0x "de manual").
        if direction == Signal.BUY:
            return is_hammer(candle, min_wick_to_body=self.rejection_wick_ratio)
        return is_shooting_star(candle, min_wick_to_body=self.rejection_wick_ratio)

    @staticmethod
    def _is_confirmation_candle(candle: pd.Series, direction: Signal) -> bool:
        # Vela que cierra a favor de la direccion esperada - sin exigencia
        # extra sobre cuanto tiene que cerrar (ver v1 para el historial de
        # por que se saco ese requisito).
        return candle["close"] > candle["open"] if direction == Signal.BUY else candle["close"] < candle["open"]

    def _rsi_extreme_and_turn(
        self, rsi_series: pd.Series, rejection_idx: int, confirmation_idx: int, direction: Signal
    ) -> bool:
        """Puntos 2 y 3 de la seccion 4: extremo real tocado + giro ya confirmado.

        Busca, en una ventana de `extreme_lookback` velas terminando en la
        vela de rechazo (inclusive), si el RSI llego a tocar la zona extrema
        (<=30 sobreventa o >=70 sobrecompra). Si la toco, exige que para la
        vela de confirmacion el RSI ya haya cruzado de vuelta el umbral (no
        que siga en la zona extrema). No se exige que el cruce ocurra
        justo entre rechazo y confirmacion: en los casos reales la
        recuperacion del RSI es progresiva a lo largo de varias velas antes
        de que aparezca el patron de rechazo/confirmacion sobre el nivel.
        """
        window_start = max(0, confirmation_idx - self.extreme_lookback)
        window = rsi_series.iloc[window_start : rejection_idx + 1]
        if window.empty or window.isna().all():
            return False
        rsi_confirmation = rsi_series.iloc[confirmation_idx]
        if pd.isna(rsi_confirmation):
            return False
        if direction == Signal.BUY:
            extreme_touched = (window <= self.rsi_oversold).any()
            already_turned = rsi_confirmation > self.rsi_oversold
        else:
            extreme_touched = (window >= self.rsi_overbought).any()
            already_turned = rsi_confirmation < self.rsi_overbought
        return bool(extreme_touched and already_turned)

    @staticmethod
    def _volume_series(data: pd.DataFrame) -> pd.Series | None:
        for column in _VOLUME_COLUMNS:
            if column in data.columns:
                return data[column].astype(float)
        return None

    def _volume_confirmed(self, volume_series: pd.Series | None, idx: int) -> bool:
        # Punto 4.1: "volumen" como uno de los 4 elementos que siempre se
        # combinan. Si no hay columna de volumen en los datos (backtests
        # sobre CSV de Twelve Data, que no la trae) no se puede exigir nada
        # -> no bloquea. En vivo, MT5 siempre entrega tick_volume.
        if volume_series is None:
            return True
        volume_ma = volume_series.rolling(
            self.volume_ma_period, min_periods=max(2, self.volume_ma_period // 2)
        ).mean()
        ma_at_idx = volume_ma.iloc[idx]
        if pd.isna(ma_at_idx) or ma_at_idx <= 0:
            return True
        return volume_series.iloc[idx] >= self.volume_confirmation_mult * ma_at_idx

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
