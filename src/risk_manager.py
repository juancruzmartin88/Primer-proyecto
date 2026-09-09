"""Gestion de riesgo: la parte mas importante del bot.

Ninguna senal de estrategia llega al broker sin pasar por aca. El objetivo
no es maximizar ganancias, es que ningun escenario individual (una racha
perdedora, un error de la estrategia, un movimiento violento del mercado)
pueda romper la cuenta.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from loguru import logger

from src.config import RiskConfig


class RiskLimitExceeded(Exception):
    """Se dispara cuando una operacion violaria un limite de riesgo."""


@dataclass
class DailyPnLTracker:
    """Lleva la cuenta de la perdida/ganancia del dia para el kill switch."""

    day: date = field(default_factory=date.today)
    realized_pnl: float = 0.0

    def register(self, pnl: float) -> None:
        today = date.today()
        if today != self.day:
            # Nuevo dia: se reinicia el contador.
            self.day = today
            self.realized_pnl = 0.0
        self.realized_pnl += pnl


class RiskManager:
    def __init__(self, config: RiskConfig, pnl_tracker: DailyPnLTracker | None = None) -> None:
        self.config = config
        self.pnl_tracker = pnl_tracker or DailyPnLTracker()

    def calculate_position_size(
        self,
        *,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float,
        pip_value_per_lot: float,
        pip_size: float,
    ) -> float:
        """Calcula el tamano de posicion (en lotes) para arriesgar un % fijo del capital.

        volumen = (balance * riesgo%) / (distancia_al_SL_en_pips * valor_pip_por_lote)
        """
        if stop_loss_price == entry_price:
            raise RiskLimitExceeded("El stop loss no puede ser igual al precio de entrada.")

        risk_amount = account_balance * (self.config.risk_per_trade_pct / 100.0)
        stop_distance_pips = abs(entry_price - stop_loss_price) / pip_size
        if stop_distance_pips <= 0:
            raise RiskLimitExceeded("Distancia de stop loss invalida (<= 0 pips).")

        raw_volume = risk_amount / (stop_distance_pips * pip_value_per_lot)
        # Redondeo conservador a 2 decimales (pasos de 0.01 lotes, tipico en Exness).
        volume = max(0.01, round(raw_volume, 2))
        logger.debug(
            "Position sizing: balance={} riesgo%={} sl_pips={:.1f} -> volumen={}",
            account_balance,
            self.config.risk_per_trade_pct,
            stop_distance_pips,
            volume,
        )
        return volume

    def check_daily_loss_limit(self, account_balance: float) -> None:
        """Corta el bot si ya se perdio el % maximo permitido en el dia (kill switch)."""
        max_loss_amount = account_balance * (self.config.max_daily_loss_pct / 100.0)
        if self.pnl_tracker.realized_pnl <= -max_loss_amount:
            raise RiskLimitExceeded(
                f"Kill switch activado: perdida del dia ({self.pnl_tracker.realized_pnl:.2f}) "
                f"alcanzo el limite de {self.config.max_daily_loss_pct}% del balance "
                f"({-max_loss_amount:.2f})."
            )

    def check_open_positions_limit(self, current_open_positions: int) -> None:
        if current_open_positions >= self.config.max_open_positions:
            raise RiskLimitExceeded(
                f"Ya hay {current_open_positions} posiciones abiertas, "
                f"el limite configurado es {self.config.max_open_positions}."
            )
