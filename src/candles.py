"""Deteccion de patrones de velas japonesas, nombrados formalmente.

Cubre los 4 patrones que el sistema exige mencionar por su nombre formal
(seccion 3, punto 4): martillo, estrella fugaz, envolvente y doji.

Cada funcion recibe una fila de un DataFrame OHLC (una "vela") y devuelve
un booleano. Los umbrales (relacion mecha/cuerpo, etc.) son parametrizables
para poder ajustarlos con el backtest en vez de dejarlos hardcodeados
sin justificacion.
"""
from __future__ import annotations

import pandas as pd


def _body(candle: pd.Series) -> float:
    return abs(candle["close"] - candle["open"])


def _range(candle: pd.Series) -> float:
    return candle["high"] - candle["low"]


def _upper_wick(candle: pd.Series) -> float:
    return candle["high"] - max(candle["open"], candle["close"])


def _lower_wick(candle: pd.Series) -> float:
    return min(candle["open"], candle["close"]) - candle["low"]


def is_hammer(candle: pd.Series, *, min_wick_to_body: float = 2.0, max_upper_wick_ratio: float = 0.3) -> bool:
    """Martillo: mecha inferior larga, cuerpo pequeno arriba, mecha superior chica.

    Senal de rechazo alcista (precio bajo durante la vela y cerro cerca del maximo).
    """
    rng = _range(candle)
    if rng <= 0:
        return False
    body = _body(candle)
    lower_wick = _lower_wick(candle)
    upper_wick = _upper_wick(candle)
    if body == 0:
        body = rng * 0.01  # evita division por cero en doji perfecto
    return (
        lower_wick >= min_wick_to_body * body
        and upper_wick <= max_upper_wick_ratio * rng
    )


def is_shooting_star(candle: pd.Series, *, min_wick_to_body: float = 2.0, max_lower_wick_ratio: float = 0.3) -> bool:
    """Estrella fugaz: mecha superior larga, cuerpo pequeno abajo, mecha inferior chica.

    Senal de rechazo bajista (precio subio durante la vela y cerro cerca del minimo).
    """
    rng = _range(candle)
    if rng <= 0:
        return False
    body = _body(candle)
    lower_wick = _lower_wick(candle)
    upper_wick = _upper_wick(candle)
    if body == 0:
        body = rng * 0.01
    return (
        upper_wick >= min_wick_to_body * body
        and lower_wick <= max_lower_wick_ratio * rng
    )


def is_doji(candle: pd.Series, *, max_body_ratio: float = 0.1) -> bool:
    """Doji: cuerpo minimo respecto al rango total de la vela (indecision)."""
    rng = _range(candle)
    if rng <= 0:
        return False
    return _body(candle) <= max_body_ratio * rng


def is_bullish_engulfing(prev_candle: pd.Series, candle: pd.Series) -> bool:
    """Envolvente alcista: vela bajista seguida de una alcista que la engulle."""
    prev_bearish = prev_candle["close"] < prev_candle["open"]
    curr_bullish = candle["close"] > candle["open"]
    engulfs = candle["open"] <= prev_candle["close"] and candle["close"] >= prev_candle["open"]
    return prev_bearish and curr_bullish and engulfs


def is_bearish_engulfing(prev_candle: pd.Series, candle: pd.Series) -> bool:
    """Envolvente bajista: vela alcista seguida de una bajista que la engulle."""
    prev_bullish = prev_candle["close"] > prev_candle["open"]
    curr_bearish = candle["close"] < candle["open"]
    engulfs = candle["open"] >= prev_candle["close"] and candle["close"] <= prev_candle["open"]
    return prev_bullish and curr_bearish and engulfs
