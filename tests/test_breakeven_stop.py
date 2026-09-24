from src.breakeven_stop import breakeven_stop_price
from src.types import Signal


def test_no_move_before_threshold_buy():
    # Entrada 100, TP 110 (distancia 10) - a 100.4 el precio recorrio solo
    # 4% del camino al TP, muy por debajo del umbral 50%.
    result = breakeven_stop_price(
        direction=Signal.BUY,
        entry_price=100.0,
        take_profit_price=110.0,
        favorable_price=100.4,
        trigger_pct=0.5,
        buffer=1.0,
    )
    assert result is None


def test_moves_to_breakeven_plus_buffer_when_threshold_reached_buy():
    # 50% de 10 = 5 -> a partir de 105.0 se activa. SL nuevo: entrada + 1.
    result = breakeven_stop_price(
        direction=Signal.BUY,
        entry_price=100.0,
        take_profit_price=110.0,
        favorable_price=105.0,
        trigger_pct=0.5,
        buffer=1.0,
    )
    assert result == 101.0


def test_moves_to_breakeven_minus_buffer_when_threshold_reached_sell():
    # Entrada 100, TP 90 (distancia 10), umbral 70% -> a partir de 93.0.
    result = breakeven_stop_price(
        direction=Signal.SELL,
        entry_price=100.0,
        take_profit_price=90.0,
        favorable_price=93.0,
        trigger_pct=0.7,
        buffer=1.0,
    )
    assert result == 99.0


def test_no_move_before_threshold_sell():
    result = breakeven_stop_price(
        direction=Signal.SELL,
        entry_price=100.0,
        take_profit_price=90.0,
        favorable_price=94.0,  # solo 60% del camino, por debajo del 70%
        trigger_pct=0.7,
        buffer=1.0,
    )
    assert result is None


def test_no_move_when_reward_distance_is_zero():
    result = breakeven_stop_price(
        direction=Signal.BUY,
        entry_price=100.0,
        take_profit_price=100.0,
        favorable_price=105.0,
        trigger_pct=0.5,
        buffer=1.0,
    )
    assert result is None


def test_exactly_at_threshold_triggers():
    # Umbral inclusive: exactamente 50% ya activa (no hace falta superarlo).
    result = breakeven_stop_price(
        direction=Signal.BUY,
        entry_price=100.0,
        take_profit_price=110.0,
        favorable_price=105.0,
        trigger_pct=0.5,
        buffer=1.0,
    )
    assert result is not None
