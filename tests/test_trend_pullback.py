import json

import pandas as pd
import pytest

from src.strategies.trend_pullback import TrendPullbackStrategy
from src.types import Signal


@pytest.fixture
def levels_file(tmp_path):
    path = tmp_path / "levels.json"
    path.write_text(json.dumps({}))
    return path


def _make(levels_file, **overrides):
    params = dict(
        symbol="X",
        timeframe="H1",
        levels_path=levels_file,
        ema_period=10,
        trend_confirmation_candles=5,
        atr_period=5,
        level_proximity_atr_mult=0.5,
        rejection_wick_ratio=1.5,
        sl_atr_margin_mult=0.5,
        min_risk_reward=1.0,
        fallback_rr_multiple=2.0,
    )
    params.update(overrides)
    return TrendPullbackStrategy(**params)


def _candles(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["time"] = pd.date_range("2026-01-01", periods=len(df), freq="1h")
    return df


def _uptrend_pullback_rows(rejection_low: float = 110.3705388612019) -> list[dict]:
    # Tendencia alcista sostenida (40 velas, cierre siempre por encima de la
    # EMA(10)), seguida de un martillo cuyo low toca la zona de la EMA -
    # dist/ATR verificado numericamente para quedar dentro de la proximidad
    # default (0.5x ATR).
    closes = [100 + i * 0.3 for i in range(40)]
    rows = [dict(open=c - 0.1, high=c + 0.1, low=c - 0.2, close=c) for c in closes]
    last_close = closes[-1]
    rows.append(dict(open=last_close + 0.2, high=last_close + 0.3, low=rejection_low, close=last_close + 0.25))
    return rows


def _downtrend_pullback_rows(rejection_high: float = 129.62946113879804) -> list[dict]:
    closes = [140 - i * 0.3 for i in range(40)]
    rows = [dict(open=c + 0.1, high=c + 0.2, low=c - 0.1, close=c) for c in closes]
    last_close = closes[-1]
    rows.append(dict(open=last_close - 0.2, high=rejection_high, low=last_close - 0.3, close=last_close - 0.25))
    return rows


def test_buy_setup_in_uptrend_pullback_to_ema(levels_file):
    strategy = _make(levels_file)
    data = _candles(_uptrend_pullback_rows())

    signal = strategy.generate_signal(data)

    assert signal == Signal.BUY
    sl = strategy.stop_loss_price(data, signal)
    tp = strategy.take_profit_price(data, signal)
    entry = data["close"].iloc[-1]
    assert sl < data["low"].iloc[-1]  # apenas debajo del extremo de la vela de rechazo
    assert sl < entry < tp


def test_sell_setup_in_downtrend_pullback_to_ema(levels_file):
    strategy = _make(levels_file)
    data = _candles(_downtrend_pullback_rows())

    signal = strategy.generate_signal(data)

    assert signal == Signal.SELL
    sl = strategy.stop_loss_price(data, signal)
    tp = strategy.take_profit_price(data, signal)
    entry = data["close"].iloc[-1]
    assert sl > data["high"].iloc[-1]
    assert tp < entry < sl


def test_no_signal_when_rejection_candle_is_too_far_from_ema(levels_file):
    strategy = _make(levels_file)
    # Mismo setup de tendencia, pero el martillo queda lejos de la EMA (no
    # es un pullback real, sigue corriendo la tendencia).
    data = _candles(_uptrend_pullback_rows(rejection_low=105.0))

    assert strategy.generate_signal(data) == Signal.HOLD


def test_no_signal_when_rejection_candle_direction_contradicts_trend(levels_file):
    strategy = _make(levels_file)
    # Tendencia alcista, pero la vela de rechazo es una estrella fugaz
    # (bajista) - no esta a favor de la tendencia.
    closes = [100 + i * 0.3 for i in range(40)]
    rows = [dict(open=c - 0.1, high=c + 0.1, low=c - 0.2, close=c) for c in closes]
    last_close = closes[-1]
    # estrella fugaz cerca de la EMA en vez de martillo
    rows.append(dict(open=110.3, high=110.75, low=110.25, close=110.28))
    data = _candles(rows)

    assert strategy.generate_signal(data) == Signal.HOLD


def test_no_signal_when_trend_is_not_sustained(levels_file):
    strategy = _make(levels_file)
    # Precio oscilando cerca de la EMA sin tendencia sostenida - las
    # ultimas `trend_confirmation_candles` no quedan todas de un mismo lado.
    closes = [110.0, 109.8, 110.2, 109.9, 110.1, 109.85, 110.15] + [109.9] * 34
    rows = [dict(open=c, high=c + 0.1, low=c - 0.6, close=c) for c in closes]
    data = _candles(rows)

    assert strategy.generate_signal(data) == Signal.HOLD


def test_sl_price_raises_when_requested_signal_does_not_match_setup(levels_file):
    strategy = _make(levels_file)
    data = _candles(_uptrend_pullback_rows())

    with pytest.raises(ValueError):
        strategy.stop_loss_price(data, Signal.SELL)
