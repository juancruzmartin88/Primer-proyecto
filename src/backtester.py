"""Motor de backtesting simple sobre velas historicas (OHLC) en un DataFrame.

No pretende ser un backtester institucional (no modela slippage realista
ni libro de ordenes) pero es suficiente para descartar rapido estrategias
que no tienen ninguna ventaja estadistica antes de pasarlas a demo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.strategy_base import Strategy
from src.types import Signal


@dataclass
class BacktestResult:
    trades: list[dict] = field(default_factory=list)
    initial_balance: float = 10_000.0

    @property
    def total_pnl(self) -> float:
        return sum(t["pnl"] for t in self.trades)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t["pnl"] > 0)
        return wins / len(self.trades)

    @property
    def max_drawdown(self) -> float:
        balance = self.initial_balance
        peak = balance
        max_dd = 0.0
        for t in self.trades:
            balance += t["pnl"]
            peak = max(peak, balance)
            max_dd = max(max_dd, (peak - balance) / peak)
        return max_dd

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t["pnl"] for t in self.trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in self.trades if t["pnl"] < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    def summary(self) -> str:
        return (
            f"Trades: {len(self.trades)} | Win rate: {self.win_rate:.1%} | "
            f"PnL total: {self.total_pnl:.2f} | Profit factor: {self.profit_factor:.2f} | "
            f"Max drawdown: {self.max_drawdown:.1%}"
        )


def run_backtest(
    strategy: Strategy,
    data: pd.DataFrame,
    *,
    initial_balance: float = 10_000.0,
    pip_size: float = 0.0001,
    pip_value_per_lot: float = 10.0,
    lookback: int = 50,
    window_size: int = 200,
) -> BacktestResult:
    """Recorre `data` vela a vela, simulando entradas/salidas de la estrategia.

    Simplificacion: una sola posicion abierta a la vez, se cierra por SL/TP
    intra-vela usando high/low, tamano de posicion fijo de 1 lote (para
    aislar la calidad de las senales del sizing; el sizing real lo aplica
    el RiskManager en el bot en vivo).

    `window_size` es a proposito el mismo valor por defecto que usa
    `MT5Client.get_rates` en produccion (`count=200`): la estrategia nunca
    ve mas velas en vivo que las que le pasa el bot, asi que el backtest
    tiene que replicar esa misma ventana - si no, se estarian probando
    condiciones que la estrategia jamas va a tener disponibles quien
    corre en vivo. Como efecto secundario, tambien evita el costo O(n^2)
    de recalcular los indicadores sobre todo el historial acumulado.
    """
    result = BacktestResult(initial_balance=initial_balance)
    open_trade: dict | None = None

    for i in range(lookback, len(data)):
        window = data.iloc[max(0, i + 1 - window_size) : i + 1]
        candle = data.iloc[i]

        if open_trade is not None:
            hit_sl = (
                candle["low"] <= open_trade["sl"]
                if open_trade["signal"] == Signal.BUY
                else candle["high"] >= open_trade["sl"]
            )
            hit_tp = (
                candle["high"] >= open_trade["tp"]
                if open_trade["signal"] == Signal.BUY
                else candle["low"] <= open_trade["tp"]
            )
            if hit_sl or hit_tp:
                exit_price = open_trade["sl"] if hit_sl else open_trade["tp"]
                direction = 1 if open_trade["signal"] == Signal.BUY else -1
                pips = (exit_price - open_trade["entry"]) / pip_size * direction
                pnl = pips * pip_value_per_lot
                result.trades.append({**open_trade, "exit": exit_price, "pnl": pnl})
                open_trade = None
            continue

        signal = strategy.generate_signal(window)
        if signal in (Signal.BUY, Signal.SELL):
            entry_price = candle["close"]
            open_trade = {
                "signal": signal,
                "entry": entry_price,
                "sl": strategy.stop_loss_price(window, signal),
                "tp": strategy.take_profit_price(window, signal),
                "entry_time": candle["time"],
            }

    return result
