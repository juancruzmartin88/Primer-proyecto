import pandas as pd

from src.strategies.range_reversion import RangeReversionStrategy
from src.types import Signal


def _candles(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["time"] = pd.date_range("2026-01-01", periods=len(df), freq="1h")
    return df


def _flat_padding(n: int = 50) -> list[dict]:
    # Patron chato repetido -> ADX bajo y estable (verificado en
    # tests/test_indicators.py::test_adx_is_low_for_a_ranging_market).
    closes = [101.0, 100.8, 101.2, 100.9, 101.1] * (n // 5)
    return [dict(open=c, high=c + 0.15, low=c - 0.15, close=c) for c in closes]


def _buy_setup_rows() -> list[dict]:
    rows = _flat_padding(50)
    tail_closes = [100.6, 100.4, 100.2, 100.0, 99.9, 99.8, 99.75, 99.9]
    for i, c in enumerate(tail_closes):
        if i < len(tail_closes) - 1:
            rows.append(dict(open=c + 0.15, high=c + 0.2, low=c - 0.15, close=c))
        else:
            # martillo sobre el piso del rango (99.2)
            rows.append(dict(open=99.78, high=99.85, low=99.2, close=99.83))
    return rows


def _sell_setup_rows() -> list[dict]:
    rows = _flat_padding(50)
    tail_closes = [101.4, 101.6, 101.8, 102.0, 102.1, 102.2, 102.25, 102.1]
    for i, c in enumerate(tail_closes):
        if i < len(tail_closes) - 1:
            rows.append(dict(open=c - 0.15, high=c + 0.15, low=c - 0.2, close=c))
        else:
            # estrella fugaz sobre el techo del rango (~102.8)
            rows.append(dict(open=102.22, high=102.8, low=102.15, close=102.17))
    return rows


def _trending_then_buy_pattern_rows() -> list[dict]:
    # Mismo tipo de cola que dispara BUY en _buy_setup_rows, pero precedida
    # de una tendencia fuerte y sostenida (ADX alto) en vez de un patron
    # chato - el regimen no debe confirmar rango.
    n_trend = 50
    trend_closes = [101.0 + 0.3 * i for i in range(n_trend)]
    rows = [dict(open=c - 0.1, high=c + 0.15, low=c - 0.15, close=c) for c in trend_closes]
    last_close = rows[-1]["close"]
    tail_closes = [last_close - 0.2 * i for i in range(1, 8)]
    for i, c in enumerate(tail_closes):
        if i < len(tail_closes) - 1:
            rows.append(dict(open=c + 0.15, high=c + 0.2, low=c - 0.15, close=c))
        else:
            rows.append(dict(open=c, high=c + 0.05, low=c - 1.5, close=c + 0.03))
    return rows


def _make(**overrides) -> RangeReversionStrategy:
    params = dict(
        symbol="XAUUSDm", timeframe="H1",
        regime_confirmation_candles=8, adx_threshold=25.0,
    )
    params.update(overrides)
    return RangeReversionStrategy(**params)


def test_buy_setup_detected_in_ranging_regime_with_tp_at_range_midpoint():
    strategy = _make()
    data = _candles(_buy_setup_rows())

    signal = strategy.generate_signal(data)

    assert signal == Signal.BUY
    sl = strategy.stop_loss_price(data, signal)
    tp = strategy.take_profit_price(data, signal)
    entry = data["close"].iloc[-1]
    range_window = data.iloc[-8:]
    floor, ceiling = range_window["low"].min(), range_window["high"].max()
    assert sl < floor  # apenas afuera del piso
    assert tp == (floor + ceiling) / 2
    assert sl < entry < tp


def test_sell_setup_detected_in_ranging_regime_with_tp_at_range_midpoint():
    strategy = _make()
    data = _candles(_sell_setup_rows())

    signal = strategy.generate_signal(data)

    assert signal == Signal.SELL
    sl = strategy.stop_loss_price(data, signal)
    tp = strategy.take_profit_price(data, signal)
    entry = data["close"].iloc[-1]
    range_window = data.iloc[-8:]
    floor, ceiling = range_window["low"].min(), range_window["high"].max()
    assert sl > ceiling  # apenas afuera del techo
    assert tp == (floor + ceiling) / 2
    assert tp < entry < sl


def test_no_signal_when_adx_confirms_trend_instead_of_range():
    strategy = _make()
    data = _candles(_trending_then_buy_pattern_rows())

    # Mismo tipo de vela de rechazo que _buy_setup_rows, pero el ADX de la
    # ventana no confirma regimen de rango (tendencia sostenida antes) ->
    # el filtro de regimen debe bloquear la señal.
    assert strategy.generate_signal(data) == Signal.HOLD


def test_no_signal_when_rsi_not_near_buy_level_even_in_ranging_regime():
    strategy = _make()
    rows = _flat_padding(50)
    # Martillo geometricamente valido sobre un "piso", pero el RSI(14) no
    # llego a tocar 40 (la serie de cierres se mantuvo neutral).
    rows.append(dict(open=101.0, high=101.35, low=100.3, close=101.05))
    data = _candles(rows)

    assert strategy.generate_signal(data) == Signal.HOLD


def test_min_range_atr_mult_blocks_a_range_too_narrow_relative_to_atr():
    # Mismo setup que test_buy_setup_detected_in_ranging_regime_with_tp_at_range_midpoint
    # (ancho de rango ~3.9x el ATR ahi) - un min_range_atr_mult mas laxo lo
    # deja pasar, uno mas estricto que ese ratio lo bloquea. Agregado
    # 28/09/2026 tras ver en el backtest real que, sin este filtro, un
    # rango casi plano da un TP pegado a la entrada (RR ~0.01-0.02),
    # "ganancias" triviales que no compensan ningun riesgo real.
    data = _candles(_buy_setup_rows())
    loose = _make(min_range_atr_mult=0.5)
    strict = _make(min_range_atr_mult=10.0)

    assert loose.generate_signal(data) == Signal.BUY
    assert strict.generate_signal(data) == Signal.HOLD


def test_sl_price_raises_when_requested_signal_does_not_match_setup():
    strategy = _make()
    data = _candles(_buy_setup_rows())

    import pytest

    with pytest.raises(ValueError):
        strategy.stop_loss_price(data, Signal.SELL)
