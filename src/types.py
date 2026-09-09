"""Tipos compartidos por el resto del bot."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"
    HOLD = "HOLD"


@dataclass(frozen=True)
class TradeOrder:
    """Orden ya dimensionada y lista para enviar (o simular) al broker."""

    symbol: str
    signal: Signal
    volume: float  # en lotes
    stop_loss: float | None
    take_profit: float | None
    comment: str = "bot"
