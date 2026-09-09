import pytest

from src.config import RiskConfig
from src.risk_manager import DailyPnLTracker, RiskLimitExceeded, RiskManager


@pytest.fixture
def risk_manager() -> RiskManager:
    config = RiskConfig(risk_per_trade_pct=1.0, max_daily_loss_pct=3.0, max_open_positions=1)
    return RiskManager(config)


def test_position_size_risks_exactly_configured_percentage(risk_manager: RiskManager):
    # Balance 10000, riesgo 1% = 100 USD. SL a 20 pips, pip value 10 USD/lote.
    # volumen esperado = 100 / (20 * 10) = 0.5 lotes.
    volume = risk_manager.calculate_position_size(
        account_balance=10_000,
        entry_price=1.1000,
        stop_loss_price=1.0980,  # 20 pips
        pip_value_per_lot=10.0,
        pip_size=0.0001,
    )
    assert volume == pytest.approx(0.5, abs=0.01)


def test_position_size_rejects_zero_distance_stop(risk_manager: RiskManager):
    with pytest.raises(RiskLimitExceeded):
        risk_manager.calculate_position_size(
            account_balance=10_000,
            entry_price=1.1000,
            stop_loss_price=1.1000,
            pip_value_per_lot=10.0,
            pip_size=0.0001,
        )


def test_position_size_has_minimum_floor(risk_manager: RiskManager):
    # Riesgo tan chico que el calculo daria menos de 0.01 lotes: se pisa al minimo.
    volume = risk_manager.calculate_position_size(
        account_balance=100,
        entry_price=1.1000,
        stop_loss_price=1.0000,  # 1000 pips
        pip_value_per_lot=10.0,
        pip_size=0.0001,
    )
    assert volume == 0.01


def test_daily_loss_kill_switch_triggers(risk_manager: RiskManager):
    tracker = DailyPnLTracker()
    tracker.register(-350.0)  # 3.5% de 10000, supera el limite de 3%
    risk_manager.pnl_tracker = tracker

    with pytest.raises(RiskLimitExceeded):
        risk_manager.check_daily_loss_limit(account_balance=10_000)


def test_daily_loss_kill_switch_does_not_trigger_below_limit(risk_manager: RiskManager):
    tracker = DailyPnLTracker()
    tracker.register(-100.0)  # 1%, por debajo del limite de 3%
    risk_manager.pnl_tracker = tracker

    risk_manager.check_daily_loss_limit(account_balance=10_000)  # no debe lanzar


def test_open_positions_limit(risk_manager: RiskManager):
    risk_manager.check_open_positions_limit(current_open_positions=0)  # no debe lanzar
    with pytest.raises(RiskLimitExceeded):
        risk_manager.check_open_positions_limit(current_open_positions=1)
