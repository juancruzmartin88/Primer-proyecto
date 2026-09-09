"""Interfaz que debe implementar cualquier estrategia del bot."""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from src.types import Signal


class Strategy(ABC):
    """Contrato minimo: recibe velas historicas y devuelve una senal.

    `data` es un DataFrame con columnas al menos: time, open, high, low,
    close, tick_volume (mismo formato que devuelve MetaTrader5.copy_rates_from_pos).
    La ultima fila es la vela mas reciente cerrada.
    """

    #: Simbolo e intervalo que esta estrategia espera operar.
    symbol: str
    timeframe: str

    @abstractmethod
    def generate_signal(self, data: pd.DataFrame) -> Signal:
        ...

    @abstractmethod
    def stop_loss_price(self, data: pd.DataFrame, signal: Signal) -> float:
        ...

    @abstractmethod
    def take_profit_price(self, data: pd.DataFrame, signal: Signal) -> float:
        ...
