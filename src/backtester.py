"""Motor de backtesting simple sobre velas historicas (OHLC) en un DataFrame.

No pretende ser un backtester institucional (no modela slippage realista
ni libro de ordenes) pero es suficiente para descartar rapido estrategias
que no tienen ninguna ventaja estadistica antes de pasarlas a demo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
from loguru import logger

from src.breakeven_stop import DEFAULT_BREAKEVEN_BUFFER, DEFAULT_TRIGGER_PCT, breakeven_stop_price
from src.indicators import atr, rsi
from src.risk_manager import RiskLimitExceeded, RiskManager
from src.strategy_base import Strategy
from src.time_exit import DEFAULT_MAX_HOURS_OPEN, DEFAULT_STALL_ATR_MULT, should_force_close
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
    risk_manager: RiskManager | None = None,
    min_lot: float = 0.01,
    lot_step: float = 0.01,
    is_real_account: bool = False,
    enable_time_exit: bool = False,
    max_hours_open: float = DEFAULT_MAX_HOURS_OPEN,
    stall_atr_mult: float = DEFAULT_STALL_ATR_MULT,
    enable_breakeven_stop: bool = False,
    breakeven_trigger_pct: float = DEFAULT_TRIGGER_PCT,
    breakeven_buffer: float = DEFAULT_BREAKEVEN_BUFFER,
) -> BacktestResult:
    """Recorre `data` vela a vela, simulando entradas/salidas de la estrategia.

    Simplificacion: una sola posicion abierta a la vez, se cierra por SL/TP
    intra-vela usando high/low.

    Sin `risk_manager`: tamano de posicion fijo de 1 lote, para aislar la
    calidad de las senales del sizing (util para comparar variantes de la
    estrategia entre si, pero el drawdown en USD/% que da NO es realista).

    Con `risk_manager`: aplica la misma regla de riesgo que el bot en vivo
    (RiskManager.calculate_position_size + enforce_min_lot_policy) sobre un
    balance que va cambiando con cada trade cerrado - asi el drawdown
    reportado es el que realmente tendrias operando con tu % de riesgo real
    sobre `initial_balance`, no un artefacto del lote fijo.

    `window_size` es a proposito el mismo valor por defecto que usa
    `MT5Client.get_rates` en produccion (`count=200`): la estrategia nunca
    ve mas velas en vivo que las que le pasa el bot, asi que el backtest
    tiene que replicar esa misma ventana - si no, se estarian probando
    condiciones que la estrategia jamas va a tener disponibles quien
    corre en vivo. Como efecto secundario, tambien evita el costo O(n^2)
    de recalcular los indicadores sobre todo el historial acumulado.

    `enable_time_exit` simula la regla de limite de tiempo de
    `src.time_exit.should_force_close` (seccion 6.1 del sistema,
    17/09/2026): si una posicion sigue abierta despues de `max_hours_open`
    sin acercarse a TP/SL, se cierra al precio de cierre de esa vela. Usa
    `rsi_period`/`atr_period` de la propia `strategy` para los indicadores
    de la regla (los mismos que ya usa para generar señales).

    `enable_breakeven_stop` simula la regla de `src.breakeven_stop`
    (24/09/2026): cuando el precio mas favorable de la vela (high para
    BUY, low para SELL) alcanza `breakeven_trigger_pct` de la distancia
    ORIGINAL entrada-TP, el SL sube a entrada + `breakeven_buffer` (una
    sola vez, nunca se mueve en contra) - se evalua ANTES de chequear
    hit_sl/hit_tp de la misma vela, asi que una vela que toca el umbral y
    despues revierte contra el nuevo SL en la misma vela cuenta como
    salida a breakeven, no como TP ni como el SL original (misma
    simplificacion de "SL con prioridad sobre TP en la misma vela" que ya
    usa el motor).
    """
    result = BacktestResult(initial_balance=initial_balance)
    balance = initial_balance
    open_trade: dict | None = None

    for i in range(lookback, len(data)):
        window = data.iloc[max(0, i + 1 - window_size) : i + 1]
        candle = data.iloc[i]

        if open_trade is not None:
            if enable_breakeven_stop:
                favorable_price = candle["high"] if open_trade["signal"] == Signal.BUY else candle["low"]
                new_sl = breakeven_stop_price(
                    direction=open_trade["signal"],
                    entry_price=open_trade["entry"],
                    take_profit_price=open_trade["tp"],
                    favorable_price=favorable_price,
                    trigger_pct=breakeven_trigger_pct,
                    buffer=breakeven_buffer,
                )
                if new_sl is not None:
                    if open_trade["signal"] == Signal.BUY:
                        open_trade["sl"] = max(open_trade["sl"], new_sl)
                    else:
                        open_trade["sl"] = min(open_trade["sl"], new_sl)
                    open_trade["breakeven_applied"] = True

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
            forced_by_time = False
            if not (hit_sl or hit_tp) and enable_time_exit:
                rsi_series = rsi(window["close"], period=strategy.rsi_period)
                atr_series = atr(window, period=strategy.atr_period)
                current_rsi = rsi_series.iloc[-1]
                current_atr = atr_series.iloc[-1]
                if not pd.isna(current_rsi) and not pd.isna(current_atr):
                    forced_by_time = should_force_close(
                        direction=open_trade["signal"],
                        entry_price=open_trade["entry"],
                        entry_time=open_trade["entry_time"],
                        current_time=candle["time"],
                        current_price=candle["close"],
                        current_rsi=current_rsi,
                        current_atr=current_atr,
                        max_hours_open=max_hours_open,
                        stall_atr_mult=stall_atr_mult,
                    )
            if hit_sl or hit_tp or forced_by_time:
                exit_price = open_trade["sl"] if hit_sl else open_trade["tp"] if hit_tp else candle["close"]
                direction = 1 if open_trade["signal"] == Signal.BUY else -1
                pips = (exit_price - open_trade["entry"]) / pip_size * direction
                pnl = pips * pip_value_per_lot * open_trade["volume"]
                balance += pnl
                if hit_sl:
                    exit_reason = "breakeven" if open_trade["breakeven_applied"] else "sl"
                else:
                    exit_reason = "tp" if hit_tp else "tiempo"
                result.trades.append({**open_trade, "exit": exit_price, "pnl": pnl, "exit_reason": exit_reason})
                open_trade = None
            continue

        signal = strategy.generate_signal(window)
        if signal in (Signal.BUY, Signal.SELL):
            entry_price = candle["close"]
            sl_price = strategy.stop_loss_price(window, signal)
            tp_price = strategy.take_profit_price(window, signal)

            volume = 1.0
            if risk_manager is not None:
                try:
                    size_result = risk_manager.calculate_position_size(
                        account_balance=balance,
                        entry_price=entry_price,
                        stop_loss_price=sl_price,
                        pip_value_per_lot=pip_value_per_lot,
                        pip_size=pip_size,
                        min_lot=min_lot,
                        lot_step=lot_step,
                    )
                    risk_manager.enforce_min_lot_policy(size_result, is_real_account=is_real_account)
                except RiskLimitExceeded as exc:
                    logger.debug("Trade descartado por gestion de riesgo: {}", exc)
                    continue
                volume = size_result.volume

            open_trade = {
                "signal": signal,
                "entry": entry_price,
                "sl": sl_price,
                "tp": tp_price,
                "volume": volume,
                "entry_time": candle["time"],
                "breakeven_applied": False,
            }

    return result
