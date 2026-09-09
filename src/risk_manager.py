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


@dataclass(frozen=True)
class PositionSizeResult:
    volume: float
    target_risk_pct: float
    actual_risk_amount: float
    actual_risk_pct: float
    # True cuando el lote minimo del instrumento obliga a arriesgar mas de
    # lo que el % de riesgo configurado permitiria (tipico en Oro con
    # capital chico: ver seccion 4 del sistema).
    min_lot_forced: bool


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
        min_lot: float = 0.01,
        lot_step: float = 0.01,
    ) -> PositionSizeResult:
        """Calcula el tamano de posicion (en lotes) para arriesgar un % fijo del capital.

        volumen = (balance * riesgo%) / (distancia_al_SL_en_pips * valor_pip_por_lote)

        Si ese volumen queda por debajo del lote minimo del instrumento, se
        redondea hacia arriba al minimo y se marca `min_lot_forced=True` -
        es la situacion descripta en la seccion 4 del sistema (tipica en
        Oro con capital chico), que el llamador debe resolver segun sea
        cuenta demo o real (ver `enforce_min_lot_policy`).
        """
        if stop_loss_price == entry_price:
            raise RiskLimitExceeded("El stop loss no puede ser igual al precio de entrada.")

        risk_amount = account_balance * (self.config.risk_per_trade_pct / 100.0)
        stop_distance_pips = abs(entry_price - stop_loss_price) / pip_size
        if stop_distance_pips <= 0:
            raise RiskLimitExceeded("Distancia de stop loss invalida (<= 0 pips).")

        raw_volume = risk_amount / (stop_distance_pips * pip_value_per_lot)
        min_lot_forced = raw_volume < min_lot
        # Redondeo al paso de lote del broker (0.01 tipico en Exness), con piso en el minimo.
        volume = max(min_lot, round(raw_volume / lot_step) * lot_step)
        volume = round(volume, 2)

        actual_risk_amount = volume * stop_distance_pips * pip_value_per_lot
        actual_risk_pct = (actual_risk_amount / account_balance) * 100.0

        result = PositionSizeResult(
            volume=volume,
            target_risk_pct=self.config.risk_per_trade_pct,
            actual_risk_amount=actual_risk_amount,
            actual_risk_pct=actual_risk_pct,
            min_lot_forced=min_lot_forced,
        )
        logger.debug(
            "Position sizing: balance={} riesgo_objetivo%={} sl_pips={:.1f} -> {}",
            account_balance,
            self.config.risk_per_trade_pct,
            stop_distance_pips,
            result,
        )
        return result

    def enforce_min_lot_policy(self, result: PositionSizeResult, *, is_real_account: bool) -> None:
        """Aplica la regla de la seccion 4 cuando el lote minimo fuerza mas riesgo del objetivo.

        Cuenta real: bloquea la operacion (hay que reducir el SL o no entrar).
        Cuenta demo: se acepta como limitacion de entrenamiento, solo se loguea.
        """
        if not result.min_lot_forced:
            return
        message = (
            f"El lote minimo del instrumento fuerza un riesgo real de "
            f"{result.actual_risk_pct:.1f}% (objetivo: {result.target_risk_pct:.1f}%)."
        )
        if is_real_account:
            raise RiskLimitExceeded(
                f"{message} En cuenta REAL no se opera en este caso: reduci el SL, "
                "ajusta las expectativas, o esperá un setup donde el lote minimo "
                "entre dentro del riesgo objetivo."
            )
        logger.warning(
            "{} Se acepta en cuenta DEMO como limitacion estructural conocida "
            "(seccion 4 del sistema), no es un error de proceso.",
            message,
        )

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
