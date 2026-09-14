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


def _make_strategy(symbol: str, levels_file, **overrides) -> StructuralPullbackStrategy:
    # Periodos chicos para que el setup se pueda armar con pocas velas y sea
    # facil de verificar a mano; la logica es la misma que en produccion.
    params = dict(
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
        extreme_lookback=5,
    )
    params.update(overrides)
    return StructuralPullbackStrategy(**params)


def _candles(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["time"] = pd.date_range("2024-01-01", periods=len(df), freq="1h")
    return df


def _buy_setup_rows(*, confirmation_close: float = 102.3) -> list[dict]:
    # Metodologia v2: caida hacia el soporte 100.0 que empuja el RSI(3) por
    # debajo de 30 (sobreventa real), pullback de vuelta hacia el nivel con
    # RSI ya recuperado por encima de 30, martillo de rechazo sobre el nivel
    # y vela de confirmacion alcista. Verificado numericamente (ver RSI(3)
    # de cada vela en el historial de este archivo).
    pad = [dict(open=113.0, high=113.0, low=113.0, close=113.0)] * 4
    rows = pad + [
        dict(open=113.0, high=113.1, low=112.9, close=113.0),
        dict(open=113.0, high=113.1, low=110.9, close=111.0),
        dict(open=111.0, high=111.1, low=108.9, close=109.0),
        dict(open=109.0, high=109.1, low=106.9, close=107.0),
        dict(open=107.0, high=108.0, low=106.9, close=107.8),
        dict(open=107.8, high=108.8, low=107.7, close=108.6),
        dict(open=108.6, high=109.6, low=108.5, close=109.4),
        dict(open=109.4, high=109.5, low=101.0, close=101.2),
        dict(open=101.2, high=101.3, low=100.2, close=100.4),
        dict(open=100.4, high=100.5, low=99.5, close=100.35),  # martillo (rechazo) sobre 100.0
        dict(open=100.4, high=confirmation_close + 0.2, low=100.3, close=confirmation_close),
    ]
    return rows


def _sell_setup_rows(*, confirmation_close: float = 197.7) -> list[dict]:
    # Espejo del caso BUY: suba hacia la resistencia 200.0 que empuja el
    # RSI(3) por encima de 70 (sobrecompra real), pullback de vuelta con RSI
    # ya recuperado por debajo de 70, estrella fugaz de rechazo sobre el
    # nivel y vela de confirmacion bajista.
    pad = [dict(open=187.0, high=187.0, low=187.0, close=187.0)] * 4
    rows = pad + [
        dict(open=187.0, high=187.1, low=186.9, close=187.0),
        dict(open=187.0, high=189.1, low=186.9, close=189.0),
        dict(open=189.0, high=191.1, low=188.9, close=191.0),
        dict(open=191.0, high=193.1, low=190.9, close=193.0),
        dict(open=193.0, high=193.1, low=192.0, close=192.2),
        dict(open=192.2, high=192.3, low=191.2, close=191.4),
        dict(open=191.4, high=191.5, low=190.4, close=190.6),
        dict(open=190.6, high=199.0, low=190.5, close=198.8),
        dict(open=198.8, high=199.8, low=198.7, close=199.6),
        dict(open=199.6, high=200.5, low=199.55, close=199.65),  # estrella fugaz (rechazo) sobre 200.0
        dict(open=199.6, high=199.7, low=confirmation_close - 0.2, close=confirmation_close),
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
    # esperada (seccion 4, punto 4). Si cierra bajista (close <= open) para
    # un setup de compra, no hay confirmacion -> no hay señal.
    strategy = _make_strategy("BUYSYM", levels_file)
    data = _candles(_buy_setup_rows(confirmation_close=100.3))

    assert strategy.generate_signal(data) == Signal.HOLD


def test_no_setup_when_rsi_never_touched_extreme_zone(levels_file):
    # Metodologia v2 (seccion 4, puntos 2 y 3): no alcanza con un pullback
    # hacia el nivel y un martillo - el RSI tiene que haber tocado
    # sobreventa/sobrecompra real (<=30 / >=70) y ya haber girado de vuelta.
    # Este caso oscila cerca del nivel sin bajar nunca de RSI 30 -> HOLD,
    # aunque el martillo y la confirmacion esten geometricamente bien.
    pad = [dict(open=100.5, high=100.5, low=100.5, close=100.5)] * 5
    rows = pad + [
        dict(open=100.5, high=101.0, low=100.4, close=100.9),
        dict(open=100.9, high=101.0, low=100.3, close=100.5),
        dict(open=100.5, high=101.1, low=100.4, close=100.8),
        dict(open=100.8, high=100.9, low=100.2, close=100.4),
        dict(open=100.4, high=101.0, low=100.3, close=100.7),
        dict(open=100.7, high=100.8, low=100.1, close=100.3),
        dict(open=100.3, high=100.9, low=100.2, close=100.6),
        dict(open=100.6, high=100.7, low=99.9, close=100.2),
        dict(open=100.2, high=100.3, low=99.5, close=100.15),  # "martillo" geometrico, pero sin RSI extremo detras
        dict(open=100.2, high=101.5, low=100.1, close=101.3),
    ]
    strategy = _make_strategy("BUYSYM", levels_file)
    data = _candles(rows)

    assert strategy.generate_signal(data) == Signal.HOLD


def test_no_setup_when_volume_is_below_average(levels_file):
    # Punto 4.1: el volumen es uno de los 4 elementos que siempre se
    # combinan. Con volumen por debajo del promedio en la vela de rechazo,
    # el setup (geometricamente valido) se descarta igual.
    strategy = _make_strategy("BUYSYM", levels_file, volume_ma_period=5, volume_confirmation_mult=1.0)
    data = _candles(_buy_setup_rows())
    data["tick_volume"] = 100
    data.loc[13, "tick_volume"] = 50  # vela de rechazo con volumen flojo

    assert strategy.generate_signal(data) == Signal.HOLD


def test_setup_detected_with_volume_above_average(levels_file):
    strategy = _make_strategy("BUYSYM", levels_file, volume_ma_period=5, volume_confirmation_mult=1.0)
    data = _candles(_buy_setup_rows())
    data["tick_volume"] = 100
    data.loc[13, "tick_volume"] = 500  # vela de rechazo con volumen fuerte

    assert strategy.generate_signal(data) == Signal.BUY


def test_no_setup_without_enough_history(levels_file):
    strategy = _make_strategy("BUYSYM", levels_file)
    data = _candles(_buy_setup_rows()).tail(5).reset_index(drop=True)

    assert strategy.generate_signal(data) == Signal.HOLD


def test_stop_loss_price_raises_without_prior_signal(levels_file):
    strategy = _make_strategy("BUYSYM", levels_file)
    data = _candles(_buy_setup_rows(confirmation_close=100.3))  # sin confirmacion -> setup invalido -> HOLD

    with pytest.raises(ValueError):
        strategy.stop_loss_price(data, Signal.BUY)
