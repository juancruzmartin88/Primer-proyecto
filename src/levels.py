"""Niveles estructurales (soporte/resistencia) por simbolo.

Segun lo definido con el usuario: primero se usan los niveles que el
carga a mano (los que el lee en TradingView: soportes, resistencias,
claviculares de H-C-H, pivotes), y si no cargo ninguno para ese simbolo,
se cae a una deteccion automatica por fractales/swings como respaldo.

Los niveles manuales viven en un JSON versionado en el repo
(config/levels.json por defecto) para que sea facil de editar sin tocar
codigo y quede historial de cambios en git.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DEFAULT_LEVELS_PATH = Path("config/levels.json")


def load_manual_levels(symbol: str, path: Path | str = DEFAULT_LEVELS_PATH) -> list[float]:
    """Lee los niveles manuales de `path` para `symbol`. Devuelve [] si no hay archivo o entrada."""
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    levels = raw.get(symbol, [])
    return sorted(float(level) for level in levels)


def detect_fractal_levels(
    data: pd.DataFrame,
    *,
    window: int = 2,
    lookback: int = 200,
) -> list[float]:
    """Detecta soportes/resistencias automaticos como fractales de Williams.

    Un maximo fractal es una vela cuyo high es el mas alto entre `window`
    velas antes y `window` velas despues (idem para minimos). Es una
    aproximacion matematica a "picos" del grafico, no una lectura de
    patron como H-C-H, pero sirve de respaldo cuando no hay niveles
    cargados a mano para el simbolo.
    """
    recent = data.tail(lookback).reset_index(drop=True)
    levels: list[float] = []
    n = len(recent)
    for i in range(window, n - window):
        window_slice = recent.iloc[i - window : i + window + 1]
        high_i = recent["high"].iloc[i]
        low_i = recent["low"].iloc[i]
        if high_i == window_slice["high"].max():
            levels.append(float(high_i))
        if low_i == window_slice["low"].min():
            levels.append(float(low_i))
    return sorted(set(levels))


def get_levels_for_symbol(
    symbol: str,
    data: pd.DataFrame,
    *,
    manual_levels_path: Path | str = DEFAULT_LEVELS_PATH,
    fractal_window: int = 2,
) -> list[float]:
    """Niveles manuales si existen para el simbolo; si no, fractales automaticos."""
    manual = load_manual_levels(symbol, manual_levels_path)
    if manual:
        return manual
    return detect_fractal_levels(data, window=fractal_window)


def nearest_level_beyond_price(
    levels: list[float], price: float, *, direction: str
) -> float | None:
    """Nivel mas cercano por encima del precio (direction='up') o por debajo ('down')."""
    if direction == "up":
        candidates = [lvl for lvl in levels if lvl > price]
        return min(candidates) if candidates else None
    candidates = [lvl for lvl in levels if lvl < price]
    return max(candidates) if candidates else None


def nearest_level_touched(
    levels: list[float], price: float, *, proximity: float
) -> float | None:
    """Nivel mas cercano dentro de `proximity` (mismas unidades que el precio) de `price`."""
    close_levels = [lvl for lvl in levels if abs(lvl - price) <= proximity]
    if not close_levels:
        return None
    return min(close_levels, key=lambda lvl: abs(lvl - price))
