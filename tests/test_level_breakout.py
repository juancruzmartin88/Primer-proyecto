import json

import pandas as pd
import pytest

from src.strategies.level_breakout import LevelBreakoutStrategy
from src.types import Signal


@pytest.fixture
def levels_file(tmp_path):
    path = tmp_path / "levels.json"
    path.write_text(json.dumps({"X": [110.0]}))
    return path


def _make(levels_file, **overrides):
    params = dict(
        symbol="X",
        timeframe="H1",
        levels_path=levels_file,
        atr_period=5,
        min_body_ratio=0.5,
        volume_ma_period=10,
        volume_breakout_mult=1.5,
        sl_atr_margin_mult=0.3,
        min_risk_reward=1.0,
        fallback_rr_multiple=2.0,
    )
    params.update(overrides)
    return LevelBreakoutStrategy(**params)


def _base_rows(n: int = 220, approach_to: float = 108.0) -> list[dict]:
    # Historial largo (para pasar min_history, que depende del lookback de
    # fractales de 200 velas) con un acercamiento gradual al nivel manual
    # (110.0) sin llegar a romperlo todavia.
    rows = []
    for i in range(n):
        c = 90.0 + (approach_to - 90.0) * (i / n)
        rows.append(dict(open=c - 0.2, high=c + 0.4, low=c - 0.4, close=c + 0.1, volume=100.0))
    return rows


def _candles(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["time"] = pd.date_range("2026-01-01", periods=len(df), freq="1h")
    return df


def test_buy_setup_on_confirmed_breakout_above_manual_level_with_volume(levels_file):
    rows = _base_rows()
    level = 110.0
    # Vela de ruptura: cuerpo real por encima del nivel, volumen alto.
    rows.append(dict(open=level - 0.2, high=level + 1.5, low=level - 0.3, close=level + 1.4, volume=300.0))
    # Vela de confirmacion: sigue cerrando por encima del nivel.
    rows.append(dict(open=level + 1.4, high=level + 2.0, low=level + 1.2, close=level + 1.8, volume=150.0))
    data = _candles(rows)
    strategy = _make(levels_file)

    signal = strategy.generate_signal(data)

    assert signal == Signal.BUY
    sl = strategy.stop_loss_price(data, signal)
    tp = strategy.take_profit_price(data, signal)
    entry = data["close"].iloc[-1]
    assert sl < level
    assert sl < entry < tp


def test_no_signal_when_breakout_candle_is_mostly_wick(levels_file):
    rows = _base_rows()
    level = 110.0
    rows.append(dict(open=level - 0.05, high=level + 2.0, low=level - 1.5, close=level + 0.1, volume=300.0))
    rows.append(dict(open=level + 0.1, high=level + 0.5, low=level - 0.1, close=level + 0.3, volume=150.0))
    data = _candles(rows)
    strategy = _make(levels_file)

    assert strategy.generate_signal(data) == Signal.HOLD


def test_no_signal_when_volume_is_not_confirmed(levels_file):
    rows = _base_rows()
    level = 110.0
    rows.append(dict(open=level - 0.2, high=level + 1.5, low=level - 0.3, close=level + 1.4, volume=100.0))
    rows.append(dict(open=level + 1.4, high=level + 2.0, low=level + 1.2, close=level + 1.8, volume=100.0))
    data = _candles(rows)
    strategy = _make(levels_file)

    assert strategy.generate_signal(data) == Signal.HOLD


def test_no_signal_when_confirmation_candle_re_enters_the_level(levels_file):
    rows = _base_rows()
    level = 110.0
    rows.append(dict(open=level - 0.2, high=level + 1.5, low=level - 0.3, close=level + 1.4, volume=300.0))
    # La vela de confirmacion vuelve a meterse adentro del nivel roto.
    rows.append(dict(open=level + 1.4, high=level + 1.5, low=level - 0.5, close=level - 0.2, volume=150.0))
    data = _candles(rows)
    strategy = _make(levels_file)

    assert strategy.generate_signal(data) == Signal.HOLD


def test_sell_setup_on_confirmed_breakdown_below_manual_level_with_volume(levels_file):
    rows = _base_rows(approach_to=92.0)
    level = 90.0

    def _fractal_pad(rows):
        rows.append(dict(open=level + 1.0, high=level + 1.5, low=level + 0.5, close=level + 0.8, volume=100.0))
        return rows

    rows = _fractal_pad(rows)
    rows.append(dict(open=level + 0.2, high=level + 0.3, low=level - 1.5, close=level - 1.4, volume=300.0))
    rows.append(dict(open=level - 1.4, high=level - 1.2, low=level - 2.0, close=level - 1.8, volume=150.0))
    data = _candles(rows)
    strategy = _make(levels_file, levels_path=levels_file)
    # Nivel manual de la fixture es 110.0 (por encima), asi que para este
    # caso agregamos ademas un nivel manual de soporte en 90.0.
    levels_file.write_text(json.dumps({"X": [90.0, 110.0]}))

    signal = strategy.generate_signal(data)

    assert signal == Signal.SELL
    sl = strategy.stop_loss_price(data, signal)
    tp = strategy.take_profit_price(data, signal)
    entry = data["close"].iloc[-1]
    assert sl > level
    assert tp < entry < sl


def test_no_volume_column_does_not_block_the_signal(levels_file):
    rows = _base_rows()
    for r in rows:
        del r["volume"]
    level = 110.0
    rows.append(dict(open=level - 0.2, high=level + 1.5, low=level - 0.3, close=level + 1.4))
    rows.append(dict(open=level + 1.4, high=level + 2.0, low=level + 1.2, close=level + 1.8))
    data = _candles(rows)
    strategy = _make(levels_file)

    assert strategy.generate_signal(data) == Signal.BUY


def test_sl_price_raises_when_requested_signal_does_not_match_setup(levels_file):
    rows = _base_rows()
    level = 110.0
    rows.append(dict(open=level - 0.2, high=level + 1.5, low=level - 0.3, close=level + 1.4, volume=300.0))
    rows.append(dict(open=level + 1.4, high=level + 2.0, low=level + 1.2, close=level + 1.8, volume=150.0))
    data = _candles(rows)
    strategy = _make(levels_file)

    with pytest.raises(ValueError):
        strategy.stop_loss_price(data, Signal.SELL)


def test_no_signal_below_min_history(levels_file):
    rows = _base_rows(n=50)
    level = 110.0
    rows.append(dict(open=level - 0.2, high=level + 1.5, low=level - 0.3, close=level + 1.4, volume=300.0))
    rows.append(dict(open=level + 1.4, high=level + 2.0, low=level + 1.2, close=level + 1.8, volume=150.0))
    data = _candles(rows)
    strategy = _make(levels_file)

    assert strategy.generate_signal(data) == Signal.HOLD
