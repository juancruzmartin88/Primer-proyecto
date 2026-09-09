"""Estrategia de ejemplo (PLACEHOLDER) para validar el esqueleto end-to-end.

Cruce de medias moviles simples: compra cuando la SMA rapida cruza hacia
arriba a la SMA lenta, vende cuando cruza hacia abajo. NO esta pensada
para llevarse a cuenta real tal cual - reemplazar por la estrategia real
una vez definidas sus reglas exactas.
"""
from __future__ import annotations

import pandas as pd

from src.strategy_base import Strategy
from src.types import Signal


class SmaCrossoverStrategy(Strategy):
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        fast_period: int = 9,
        slow_period: int = 21,
        stop_loss_pips: float = 20,
        take_profit_pips: float = 40,
        pip_size: float = 0.0001,
    ) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.stop_loss_pips = stop_loss_pips
        self.take_profit_pips = take_profit_pips
        self.pip_size = pip_size

    def _smas(self, data: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        fast = data["close"].rolling(self.fast_period).mean()
        slow = data["close"].rolling(self.slow_period).mean()
        return fast, slow

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if len(data) < self.slow_period + 1:
            return Signal.HOLD

        fast, slow = self._smas(data)
        prev_fast, prev_slow = fast.iloc[-2], slow.iloc[-2]
        curr_fast, curr_slow = fast.iloc[-1], slow.iloc[-1]

        crossed_up = prev_fast <= prev_slow and curr_fast > curr_slow
        crossed_down = prev_fast >= prev_slow and curr_fast < curr_slow

        if crossed_up:
            return Signal.BUY
        if crossed_down:
            return Signal.SELL
        return Signal.HOLD

    def stop_loss_price(self, data: pd.DataFrame, signal: Signal) -> float:
        last_close = data["close"].iloc[-1]
        offset = self.stop_loss_pips * self.pip_size
        return last_close - offset if signal == Signal.BUY else last_close + offset

    def take_profit_price(self, data: pd.DataFrame, signal: Signal) -> float:
        last_close = data["close"].iloc[-1]
        offset = self.take_profit_pips * self.pip_size
        return last_close + offset if signal == Signal.BUY else last_close - offset
