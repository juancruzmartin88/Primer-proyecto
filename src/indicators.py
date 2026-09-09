"""Indicadores tecnicos usados por las estrategias (RSI, ATR).

Implementados con el suavizado de Wilder (ewm con alpha=1/periodo), que es
el mismo metodo que usan MetaTrader y TradingView por defecto - importante
para que las alertas mecanicas de la seccion 8 del sistema coincidan con
lo que ve el usuario en el grafico.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


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
