import json

import pandas as pd
import pytest

from src.strategies.trend_pullback_confirmed import TrendPullbackConfirmedStrategy
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
    return TrendPullbackConfirmedStrategy(**params)


def _candles(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["time"] = pd.date_range("2026-01-01", periods=len(df), freq="1h")
    return df


def _uptrend_rows_with_rejection(rejection_low: float = 110.3705388612019) -> list[dict]:
    closes = [100 + i * 0.3 for i in range(40)]
    rows = [dict(open=c - 0.1, high=c + 0.1, low=c - 0.2, close=c) for c in closes]
    last_close = closes[-1]
    rows.append(dict(open=last_close + 0.2, high=last_close + 0.3, low=rejection_low, close=last_close + 0.25))
    return rows


def _downtrend_rows_with_rejection(rejection_high: float = 129.62946113879804) -> list[dict]:
    closes = [140 - i * 0.3 for i in range(40)]
    rows = [dict(open=c + 0.1, high=c + 0.2, low=c - 0.1, close=c) for c in closes]
    last_close = closes[-1]
    rows.append(dict(open=last_close - 0.2, high=rejection_high, low=last_close - 0.3, close=last_close - 0.25))
    return rows


def test_buy_setup_requires_bullish_confirmation_candle_after_the_hammer(levels_file):
    strategy = _make(levels_file)
    rows = _uptrend_rows_with_rejection()
    rejection_close = rows[-1]["close"]
    # Confirmacion alcista: cierra por encima de la apertura.
    rows.append(dict(open=rejection_close, high=rejection_close + 0.3, low=rejection_close - 0.05, close=rejection_close + 0.2))
    data = _candles(rows)

    signal = strategy.generate_signal(data)

    assert signal == Signal.BUY
    entry = data["close"].iloc[-1]
    rejection_low = rows[-2]["low"]
    sl = strategy.stop_loss_price(data, signal)
    tp = strategy.take_profit_price(data, signal)
    assert sl < rejection_low  # detras del extremo de la vela de RECHAZO (no la de confirmacion)
    assert sl < entry < tp


def test_no_buy_signal_when_confirmation_candle_closes_bearish(levels_file):
    strategy = _make(levels_file)
    rows = _uptrend_rows_with_rejection()
    rejection_close = rows[-1]["close"]
    # Martillo geometricamente valido, pero la vela SIGUIENTE cierra en contra.
    rows.append(dict(open=rejection_close + 0.1, high=rejection_close + 0.15, low=rejection_close - 0.2, close=rejection_close - 0.1))
    data = _candles(rows)

    assert strategy.generate_signal(data) == Signal.HOLD


def test_sell_setup_requires_bearish_confirmation_candle_after_the_shooting_star(levels_file):
    strategy = _make(levels_file)
    rows = _downtrend_rows_with_rejection()
    rejection_close = rows[-1]["close"]
    rows.append(dict(open=rejection_close, high=rejection_close + 0.05, low=rejection_close - 0.3, close=rejection_close - 0.2))
    data = _candles(rows)

    signal = strategy.generate_signal(data)

    assert signal == Signal.SELL
    entry = data["close"].iloc[-1]
    rejection_high = rows[-2]["high"]
    sl = strategy.stop_loss_price(data, signal)
    tp = strategy.take_profit_price(data, signal)
    assert sl > rejection_high
    assert tp < entry < sl


def test_no_sell_signal_when_confirmation_candle_closes_bullish(levels_file):
    strategy = _make(levels_file)
    rows = _downtrend_rows_with_rejection()
    rejection_close = rows[-1]["close"]
    rows.append(dict(open=rejection_close - 0.1, high=rejection_close + 0.2, low=rejection_close - 0.15, close=rejection_close + 0.1))
    data = _candles(rows)

    assert strategy.generate_signal(data) == Signal.HOLD


def test_min_history_is_one_more_than_base_trend_pullback_strategy(levels_file):
    from src.strategies.trend_pullback import TrendPullbackStrategy

    base = TrendPullbackStrategy(symbol="X", timeframe="H1", levels_path=levels_file, ema_period=10, trend_confirmation_candles=5, atr_period=5)
    confirmed = _make(levels_file)

    assert confirmed.min_history == base.min_history + 1
