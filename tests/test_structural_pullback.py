import json

import pandas as pd
import pytest

from src.strategies.structural_pullback import StructuralPullbackStrategy
from src.types import Signal


@pytest.fixture
def levels_file(tmp_path):
    path = tmp_path / "levels.json"
    path.write_text(json.dumps({"BUYSYM": [100.0], "SELLSYM": [200.0]}))
    return path


def _make_strategy(symbol: str, levels_file) -> StructuralPullbackStrategy:
    # Periodos chicos para que el setup se pueda armar con pocas velas y
    # sea facil de verificar a mano; la logica es la misma que en produccion.
    return StructuralPullbackStrategy(
        symbol=symbol,
        timeframe="H1",
        levels_path=levels_file,
        lookback_candles=5,
        level_proximity_atr_mult=0.5,
        atr_period=3,
        rsi_period=3,
        sl_atr_margin_mult=0.5,
        min_risk_reward=1.0,
        fallback_rr_multiple=2.0,
    )


def _candles(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["time"] = pd.date_range("2024-01-01", periods=len(df), freq="1h")
    return df


def _buy_setup_rows(*, confirmation_close: float = 103.0) -> list[dict]:
    # Downtrend hacia el soporte 100.0, pullback, martillo de rechazo,
    # confirmacion alcista. Verificado numericamente: RSI(3) pasa de 0
    # (vela de rechazo) a >50 (vela de confirmacion).
    rows = [
        dict(open=113.0, high=113.1, low=112.9, close=113.0),
        dict(open=113.0, high=113.1, low=112.4, close=112.5),
        dict(open=112.0, high=112.1, low=109.9, close=110.0),
        dict(open=110.0, high=110.1, low=107.9, close=108.0),
        dict(open=108.0, high=108.1, low=106.4, close=106.5),
        dict(open=106.5, high=106.6, low=104.9, close=105.0),
        dict(open=105.0, high=105.1, low=103.4, close=103.5),
        dict(open=103.5, high=103.6, low=101.9, close=102.0),
        dict(open=102.0, high=102.1, low=100.8, close=100.9),
        dict(open=100.9, high=101.0, low=100.7, close=100.8),
        dict(open=100.8, high=100.9, low=100.2, close=100.6),  # toca el nivel 100
        dict(open=100.5, high=100.55, low=99.5, close=100.45),  # martillo (rechazo)
        dict(open=100.5, high=confirmation_close + 0.1, low=100.4, close=confirmation_close),
    ]
    return rows


def _sell_setup_rows(*, confirmation_close: float = 197.2) -> list[dict]:
    # Espejo del caso BUY: uptrend hacia la resistencia 200.0, estrella
    # fugaz de rechazo, confirmacion bajista.
    rows = [
        dict(open=187.0, high=187.1, low=186.9, close=187.0),
        dict(open=187.0, high=187.6, low=186.9, close=187.5),
        dict(open=188.0, high=190.1, low=187.9, close=190.0),
        dict(open=190.0, high=192.1, low=189.9, close=192.0),
        dict(open=192.0, high=193.6, low=191.9, close=193.5),
        dict(open=193.5, high=195.1, low=193.4, close=195.0),
        dict(open=195.0, high=196.6, low=194.9, close=196.5),
        dict(open=196.5, high=198.1, low=196.4, close=198.0),
        dict(open=198.0, high=199.2, low=197.9, close=199.1),
        dict(open=199.1, high=199.3, low=199.0, close=199.2),
        dict(open=199.2, high=199.8, low=199.1, close=199.4),  # toca el nivel 200
        dict(open=199.5, high=200.5, low=199.45, close=199.55),  # estrella fugaz (rechazo)
        dict(open=199.5, high=199.6, low=197.0, close=confirmation_close),
    ]
    return rows


def test_buy_setup_detected_with_sl_below_pullback_and_tp_by_rr(levels_file):
    strategy = _make_strategy("BUYSYM", levels_file)
    data = _candles(_buy_setup_rows())

    signal = strategy.generate_signal(data)

    assert signal == Signal.BUY
    sl = strategy.stop_loss_price(data, signal)
    tp = strategy.take_profit_price(data, signal)
    entry = data["close"].iloc[-1]
    assert sl < data["low"].iloc[-2]  # por debajo del minimo de la vela de rechazo
    assert tp > entry  # TP en la direccion de la operacion
    # Sin nivel util mas arriba (unico nivel cargado es el soporte de 100),
    # tiene que haber caido al fallback de multiplo de riesgo.
    risk = entry - sl
    assert tp == pytest.approx(entry + 2.0 * risk, rel=1e-6)


def test_sell_setup_detected_with_sl_above_pullback_and_tp_by_rr(levels_file):
    strategy = _make_strategy("SELLSYM", levels_file)
    data = _candles(_sell_setup_rows())

    signal = strategy.generate_signal(data)

    assert signal == Signal.SELL
    sl = strategy.stop_loss_price(data, signal)
    tp = strategy.take_profit_price(data, signal)
    entry = data["close"].iloc[-1]
    assert sl > data["high"].iloc[-2]
    assert tp < entry
    risk = sl - entry
    assert tp == pytest.approx(entry - 2.0 * risk, rel=1e-6)


def test_no_setup_when_confirmation_candle_is_not_bullish(levels_file):
    # La vela de confirmacion tiene que cerrar a favor de la direccion
    # esperada (seccion 5, v2). Si cierra bajista (close <= open) para un
    # setup de compra, no hay confirmacion -> no hay señal.
    strategy = _make_strategy("BUYSYM", levels_file)
    data = _candles(_buy_setup_rows(confirmation_close=100.45))

    assert strategy.generate_signal(data) == Signal.HOLD


def test_no_setup_without_enough_history(levels_file):
    strategy = _make_strategy("BUYSYM", levels_file)
    data = _candles(_buy_setup_rows()).tail(5).reset_index(drop=True)

    assert strategy.generate_signal(data) == Signal.HOLD


def test_stop_loss_price_raises_without_prior_signal(levels_file):
    strategy = _make_strategy("BUYSYM", levels_file)
    # Movimiento demasiado chico para cruzar RSI(3) por 50 -> setup invalido -> HOLD
    data = _candles(_buy_setup_rows(confirmation_close=100.52))

    with pytest.raises(ValueError):
        strategy.stop_loss_price(data, Signal.BUY)
