"""Indicadores tecnicos usados por las estrategias (RSI, ATR).

Implementados con el suavizado de Wilder (ewm con alpha=1/periodo), que es
el mismo metodo que usan MetaTrader y TradingView por defecto - importante
para que las alertas mecanicas de la seccion 8 del sistema coincidan con
lo que ve el usuario en el grafico.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(close: pd.Series, period: int = 50) -> pd.Series:
    return close.rolling(period, min_periods=period).mean()


def ema(close: pd.Series, period: int = 50) -> pd.Series:
    """EMA estandar (span=period, no el suavizado de Wilder de rsi/atr/adx) -
    misma convencion que usa MT5/TradingView para "EMA N" en el grafico."""
    return close.ewm(span=period, min_periods=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = gains.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    # Cuando avg_loss es 0 (solo velas alcistas en la ventana), RSI = 100.
    result = result.where(avg_loss != 0, 100.0)
    return result


def true_range(data: pd.DataFrame) -> pd.Series:
    prev_close = data["close"].shift(1)
    ranges = pd.concat(
        [
            data["high"] - data["low"],
            (data["high"] - prev_close).abs(),
            (data["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = true_range(data)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def efficiency_ratio(close: pd.Series, period: int = 14) -> pd.Series:
    """Efficiency Ratio de Kaufman - 0 (puro ruido lateral) a 1 (tendencia
    perfectamente recta), usado hasta ahora solo en diagnosticos ad hoc
    (Oro/BTC, 28/09/2026) - agregado como indicador real el 30/09/2026 para
    usarlo como filtro activo (`src/regime_filter.py`), no solo lectura.

    ER = |cambio neto en `period` velas| / suma de |cambio vela a vela| en
    esa misma ventana. Numerador y denominador usan el mismo tramo de
    precio, asi que por desigualdad triangular el resultado siempre cae en
    [0, 1] - no hace falta acotarlo a mano.
    """
    net_change = (close - close.shift(period)).abs()
    volatility = close.diff().abs().rolling(period, min_periods=period).sum()
    er = net_change / volatility.replace(0, np.nan)
    # Volatilidad 0 (precio plano en toda la ventana) es el caso degenerado
    # 0/0 - no hay eficiencia que medir, se define como 0 (lateral puro).
    return er.where(volatility != 0, 0.0)


def adx(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """ADX de Wilder - fuerza de tendencia (no direccion), 0-100.

    Valores bajos (tipicamente <20-25) indican ausencia de tendencia -- lo
    usa `RangeReversionStrategy` (28/09/2026) para confirmar regimen lateral
    antes de operar reversiones sobre el rango en vez de sobre un nivel
    estructural. Mismo suavizado de Wilder que `rsi`/`atr` (ewm alpha=1/periodo).
    """
    up_move = data["high"].diff()
    down_move = -data["low"].diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr = true_range(data)
    smoothed_tr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    smoothed_plus_dm = plus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    smoothed_minus_dm = minus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    plus_di = 100 * (smoothed_plus_dm / smoothed_tr.replace(0, np.nan))
    minus_di = 100 * (smoothed_minus_dm / smoothed_tr.replace(0, np.nan))

    di_sum = plus_di + minus_di
    dx = 100 * (plus_di - minus_di).abs() / di_sum.replace(0, np.nan)
    # Sin movimiento direccional de ningun lado (di_sum == 0): no hay
    # tendencia por definicion, DX = 0 en vez de NaN.
    dx = dx.where(di_sum != 0, 0.0)

    return dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
