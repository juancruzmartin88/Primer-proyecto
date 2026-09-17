from datetime import datetime, timedelta, timezone

from src.time_exit import should_force_close
from src.types import Signal

ENTRY_TIME = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)


def _at(hours: float) -> datetime:
    return ENTRY_TIME + timedelta(hours=hours)


def test_never_forces_close_before_max_hours():
    # Aunque el RSI ya perdio el lado y el precio no se movio nada, antes
    # del umbral de horas nunca se fuerza el cierre (seccion 6.1: "limite
    # de 4 horas desde la activacion").
    result = should_force_close(
        direction=Signal.BUY,
        entry_price=100.0,
        entry_time=ENTRY_TIME,
        current_time=_at(3.9),
        current_price=100.0,
        current_rsi=40.0,
        current_atr=1.0,
    )
    assert result is False


def test_keeps_open_after_max_hours_when_trending_favorably():
    # RSI sostiene el lado de la compra (>50) y el precio ya avanzo mas de
    # 0.5x ATR a favor -> se le da mas margen, no se cierra.
    result = should_force_close(
        direction=Signal.BUY,
        entry_price=100.0,
        entry_time=ENTRY_TIME,
        current_time=_at(4.5),
        current_price=100.6,
        current_rsi=55.0,
        current_atr=1.0,
    )
    assert result is False


def test_closes_when_stalled_even_with_favorable_rsi():
    # RSI todavia del lado correcto, pero el precio practicamente no se
    # movio (lateralizando en rango angosto) -> se fuerza el cierre.
    result = should_force_close(
        direction=Signal.BUY,
        entry_price=100.0,
        entry_time=ENTRY_TIME,
        current_time=_at(5.0),
        current_price=100.1,
        current_rsi=52.0,
        current_atr=1.0,
    )
    assert result is True


def test_closes_when_rsi_lost_the_favorable_side_even_if_price_advanced():
    # El precio avanzo, pero el RSI ya perdio el lado que sostenia la tesis
    # de compra -> se fuerza el cierre igual.
    result = should_force_close(
        direction=Signal.BUY,
        entry_price=100.0,
        entry_time=ENTRY_TIME,
        current_time=_at(4.1),
        current_price=100.8,
        current_rsi=48.0,
        current_atr=1.0,
    )
    assert result is True


def test_sell_direction_mirrors_buy_logic():
    # Venta: RSI favorable es <50, avance a favor es que el precio BAJE.
    still_trending = should_force_close(
        direction=Signal.SELL,
        entry_price=100.0,
        entry_time=ENTRY_TIME,
        current_time=_at(4.2),
        current_price=99.3,
        current_rsi=45.0,
        current_atr=1.0,
    )
    assert still_trending is False

    stalled = should_force_close(
        direction=Signal.SELL,
        entry_price=100.0,
        entry_time=ENTRY_TIME,
        current_time=_at(4.2),
        current_price=99.95,
        current_rsi=45.0,
        current_atr=1.0,
    )
    assert stalled is True


def test_zero_or_negative_atr_is_treated_as_stalled():
    result = should_force_close(
        direction=Signal.BUY,
        entry_price=100.0,
        entry_time=ENTRY_TIME,
        current_time=_at(4.5),
        current_price=105.0,
        current_rsi=60.0,
        current_atr=0.0,
    )
    assert result is True
