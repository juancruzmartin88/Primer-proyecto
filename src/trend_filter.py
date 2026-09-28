"""Filtro de tendencia 4H sobre la Metodologia v2 (28/09/2026) - evaluacion puntual.

El usuario pidio evaluar si descartar señales de 1H que van en contra de la
tendencia mayor de 4H mejora el backtest de Oro. Tres formas de definir
"tendencia" pedidas explicitamente, todas calculadas sobre velas 4H
resampleadas de los mismos datos H1 (no se pide un feed 4H separado):

  (a) precio vs SMA50 en 4H - arriba = up, abajo = down.
  (b) RSI(14) en 4H vs 50 - arriba = up, abajo = down.
  (c) estructura de maximos/minimos (fractales) en las ultimas N velas 4H -
      maximo y minimo mas recientes ambos mas altos que los previos = up
      (HH+HL), ambos mas bajos = down (LH+LL), cualquier otra combinacion
      (estructura mixta) = neutral.

No modifica `StructuralPullbackStrategy` - `TrendFilteredStrategy` la
envuelve y descarta (convierte a HOLD) cualquier señal que vaya en contra
de la tendencia vigente. Una tendencia "neutral" (sin dirección clara) NO
bloquea nada - la idea del usuario es descartar señales EN CONTRA de una
tendencia mayor, no exigir que siempre haya una tendencia clara.

Sin lookahead: `map_trend_to_h1` solo usa el valor de una vela 4H a partir
del momento en que esa vela ya cerro (asof hacia atras), nunca antes.
"""
from __future__ import annotations

import pandas as pd

from src.indicators import rsi, sma
from src.levels import detect_fractal_levels
from src.strategy_base import Strategy
from src.types import Signal

_UP = "up"
_DOWN = "down"
_NEUTRAL = "neutral"


def resample_to_4h(data: pd.DataFrame) -> pd.DataFrame:
    """Resamplea velas H1 (columnas time/open/high/low/close) a velas 4H.

    `label="left"`: el timestamp de cada vela 4H es el INICIO del bloque
    (ej. la vela "2026-03-01 00:00" cubre 00:00-04:00) - importante para
    `map_trend_to_h1`, que asume esta convencion al calcular desde cuando
    esta disponible cada valor.
    """
    indexed = data.set_index("time")
    ohlc = indexed[["open", "high", "low", "close"]].resample("4h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    return ohlc.dropna().reset_index()


def trend_by_sma(data_4h: pd.DataFrame, *, period: int = 50) -> pd.Series:
    sma_series = sma(data_4h["close"], period=period)
    trend = pd.Series(_NEUTRAL, index=data_4h.index)
    trend[data_4h["close"] > sma_series] = _UP
    trend[data_4h["close"] < sma_series] = _DOWN
    trend[sma_series.isna()] = _NEUTRAL
    trend.index = data_4h["time"]
    return trend


def trend_by_rsi(data_4h: pd.DataFrame, *, period: int = 14) -> pd.Series:
    rsi_series = rsi(data_4h["close"], period=period)
    trend = pd.Series(_NEUTRAL, index=data_4h.index)
    trend[rsi_series > 50] = _UP
    trend[rsi_series < 50] = _DOWN
    trend[rsi_series.isna()] = _NEUTRAL
    trend.index = data_4h["time"]
    return trend


def trend_by_structure(data_4h: pd.DataFrame, *, lookback: int = 20, fractal_window: int = 2) -> pd.Series:
    """Estructura de maximos/minimos (fractales de Williams) en una ventana movil de `lookback` velas 4H.

    HH+HL (ultimo maximo y minimo fractal mas altos que los previos) = up.
    LH+LL (ambos mas bajos) = down. Cualquier otra combinacion = neutral
    (no hay estructura direccional clara, o menos de 2 fractales de cada
    tipo en la ventana).
    """
    trend = pd.Series(_NEUTRAL, index=data_4h.index)
    for i in range(len(data_4h)):
        window = data_4h.iloc[max(0, i + 1 - lookback) : i + 1]
        highs, lows = _fractal_highs_lows(window, fractal_window)
        if len(highs) >= 2 and len(lows) >= 2:
            if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
                trend.iloc[i] = _UP
            elif highs[-1] < highs[-2] and lows[-1] < lows[-2]:
                trend.iloc[i] = _DOWN
    trend.index = data_4h["time"]
    return trend


def _fractal_highs_lows(window: pd.DataFrame, fractal_window: int) -> tuple[list[float], list[float]]:
    n = len(window)
    highs, lows = [], []
    for i in range(fractal_window, n - fractal_window):
        slice_ = window.iloc[i - fractal_window : i + fractal_window + 1]
        high_i, low_i = window["high"].iloc[i], window["low"].iloc[i]
        if high_i == slice_["high"].max():
            highs.append(high_i)
        if low_i == slice_["low"].min():
            lows.append(low_i)
    return highs, lows


def map_trend_to_h1(h1_times: pd.Series, trend_4h: pd.Series) -> pd.Series:
    """Mapea cada timestamp H1 al ultimo valor de tendencia 4H YA CERRADO.

    `trend_4h` tiene que venir indexado por el timestamp de INICIO de cada
    vela 4H (label="left", ver `resample_to_4h`) - ese valor recien esta
    disponible 4 horas despues de ese timestamp (cuando la vela cierra), no
    antes. Sin este desplazamiento se estaria mirando el futuro.
    """
    available_from = trend_4h.index + pd.Timedelta(hours=4)
    avail_df = pd.DataFrame({"available_from": available_from, "trend": trend_4h.values}).sort_values(
        "available_from"
    )
    h1_df = pd.DataFrame({"time": pd.Series(h1_times).reset_index(drop=True)})
    merged = pd.merge_asof(
        h1_df.sort_values("time"), avail_df, left_on="time", right_on="available_from", direction="backward"
    )
    merged = merged.sort_index()
    result = merged["trend"].fillna(_NEUTRAL)
    result.index = h1_df.index
    return result


class TrendFilteredStrategy(Strategy):
    """Envuelve una estrategia base y descarta señales que van en contra de `h1_trend`.

    `h1_trend` tiene que estar indexado 0..N-1 alineado con las mismas
    filas del DataFrame completo que se le va a pasar a `run_backtest` (no
    con la ventana recortada que recibe `generate_signal` en cada vuelta) -
    se busca por el timestamp de la ultima vela de esa ventana, no por
    posicion.
    """

    def __init__(self, base: Strategy, h1_trend_by_time: dict[pd.Timestamp, str]) -> None:
        self.base = base
        self.h1_trend_by_time = h1_trend_by_time
        self.symbol = base.symbol
        self.timeframe = base.timeframe
        self.min_history = getattr(base, "min_history", 0)

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        signal = self.base.generate_signal(data)
        if signal not in (Signal.BUY, Signal.SELL):
            return signal
        current_time = data["time"].iloc[-1]
        trend = self.h1_trend_by_time.get(current_time, _NEUTRAL)
        if trend == _UP and signal == Signal.SELL:
            return Signal.HOLD
        if trend == _DOWN and signal == Signal.BUY:
            return Signal.HOLD
        return signal

    def stop_loss_price(self, data: pd.DataFrame, signal: Signal) -> float:
        return self.base.stop_loss_price(data, signal)

    def take_profit_price(self, data: pd.DataFrame, signal: Signal) -> float:
        return self.base.take_profit_price(data, signal)
