"""Niveles estructurales (soporte/resistencia) por simbolo.

Los niveles manuales (los que el usuario lee en TradingView: soportes,
resistencias, claviculares de H-C-H, pivotes) viven en un JSON versionado
en el repo (config/levels.json por defecto) para que sea facil de editar
sin tocar codigo y quede historial de cambios en git.

Hasta el 22/09/2026, `get_levels_for_symbol` usaba SOLO los manuales si
habia alguno cargado para el simbolo, cayendo a fractales automaticos
unicamente si la lista estaba vacia. Eso genero un incidente real: los
niveles de BTC se cargaron el 09/09/2026 (~77.000-79.400) y para el 22/09
el precio ya operaba a ~86.000 - a mas de 5.000 puntos de distancia. Como
la lista de BTC no estaba vacia, el respaldo automatico nunca se activaba,
y el bot quedo ciego (ninguna señal podia cumplir la condicion de "nivel
tocado") sin que nadie lo notara hasta que el usuario pregunto por que no
operaba. Ver CLAUDE.md para el detalle completo.

Desde entonces, `get_levels_for_symbol` combina SIEMPRE los dos: los
manuales (juicio del usuario, capturan zonas que un fractal reciente no
necesariamente ve) + los fractales calculados sobre las ultimas velas
(se recalculan solos en cada llamada, sin depender de que alguien los
actualice a mano). El filtro de proximidad de la estrategia
(`level_proximity_atr_mult`) ya descarta los niveles que no estan cerca
del precio actual, asi que sumar ambas fuentes no ensucia nada - en el
peor caso hay niveles de mas que nunca se usan. Esto hace que el bot ya
no dependa de que el usuario actualice el archivo para poder operar -
los manuales pasan a ser un complemento, no un requisito.
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
    """Niveles manuales + fractales automaticos, combinados (ver docstring del modulo)."""
    manual = load_manual_levels(symbol, manual_levels_path)
    fractal = detect_fractal_levels(data, window=fractal_window)
    return sorted(set(manual) | set(fractal))


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
