import json

import pandas as pd
import pytest

from src.strategies.volume_breakout import VolumeBreakoutStrategy
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
        consolidation_window=10,
        range_width_atr_mult=1.5,
        atr_period=5,
        min_body_ratio=0.5,
        volume_ma_period=10,
        volume_breakout_mult=1.5,
        sl_atr_margin_mult=0.3,
        min_risk_reward=1.0,
        fallback_rr_multiple=2.0,
    )
    params.update(overrides)
    return VolumeBreakoutStrategy(**params)


def _base_rows(n: int = 30, level: float = 100.0, half_range: float = 0.3) -> list[dict]:
    # Historial previo con rango de vela normal (para el ATR de base), luego
    # una consolidacion angosta de 10 velas alrededor de `level`.
    rows = []
    for i in range(n):
        c = level - 20 + i * 0.6  # tendencia leve, rango de vela ~1.0 (ATR normal)
        rows.append(dict(open=c - 0.3, high=c + 0.5, low=c - 0.5, close=c + 0.1, volume=100.0))
    for _ in range(10):
        rows.append(dict(open=level - 0.1, high=level + half_range, low=level - half_range, close=level, volume=100.0))
    return rows


def _candles(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["time"] = pd.date_range("2026-01-01", periods=len(df), freq="1h")
    return df


def test_buy_setup_on_real_body_breakout_with_volume(levels_file):
    rows = _base_rows()
    range_high = max(r["high"] for r in rows[-10:])
    # Vela de ruptura: cuerpo real por encima del rango, volumen alto.
    rows.append(dict(open=range_high + 0.1, high=range_high + 1.5, low=range_high, close=range_high + 1.4, volume=300.0))
    data = _candles(rows)
    strategy = _make(levels_file)

    assert strategy.generate_signal(data) == Signal.BUY


def test_no_signal_when_breakout_candle_is_mostly_wick(levels_file):
    rows = _base_rows()
    range_high = max(r["high"] for r in rows[-10:])
    # Cierra apenas afuera pero con mecha larga y cuerpo chico (doji-like).
    rows.append(dict(open=range_high + 0.05, high=range_high + 2.0, low=range_high - 1.5, close=range_high + 0.1, volume=300.0))
    data = _candles(rows)
    strategy = _make(levels_file)

    assert strategy.generate_signal(data) == Signal.HOLD


def test_no_signal_when_volume_is_not_confirmed(levels_file):
    rows = _base_rows()
    range_high = max(r["high"] for r in rows[-10:])
    rows.append(dict(open=range_high + 0.1, high=range_high + 1.5, low=range_high, close=range_high + 1.4, volume=100.0))
    data = _candles(rows)
    strategy = _make(levels_file)

    assert strategy.generate_signal(data) == Signal.HOLD


def test_no_signal_when_range_is_not_narrow_enough(levels_file):
    rows = _base_rows(n=30)
    # Las ultimas 10 velas tienen rango individual chico (mismo ATR de base
    # que el resto), pero DERIVAN varios puntos en total - un rango de
    # consolidacion "ancho" real (max-min de la ventana), no una ventana de
    # velas individualmente mas volatiles (eso ya lo reflejaria el ATR).
    drift = [0.0, 1.0, 2.0, 3.0, 4.0, 3.0, 2.0, 1.0, 0.0, -1.0]
    for d in drift:
        c = 100.0 + d
        rows.append(dict(open=c - 0.1, high=c + 0.3, low=c - 0.3, close=c + 0.1, volume=100.0))
    range_high = max(r["high"] for r in rows[-10:])
    rows.append(dict(open=range_high + 0.1, high=range_high + 1.5, low=range_high, close=range_high + 1.4, volume=300.0))
    data = _candles(rows)
    strategy = _make(levels_file)

    assert strategy.generate_signal(data) == Signal.HOLD


def test_sell_setup_on_real_body_breakdown_with_volume(levels_file):
    rows = _base_rows()
    range_low = min(r["low"] for r in rows[-10:])
    rows.append(dict(open=range_low - 0.1, high=range_low, low=range_low - 1.5, close=range_low - 1.4, volume=300.0))
    data = _candles(rows)
    strategy = _make(levels_file)

    signal = strategy.generate_signal(data)

    assert signal == Signal.SELL
    sl = strategy.stop_loss_price(data, signal)
    tp = strategy.take_profit_price(data, signal)
    entry = data["close"].iloc[-1]
    assert sl > max(r["high"] for r in rows[-11:-1])
    assert tp < entry < sl


def test_stop_loss_is_behind_the_opposite_side_of_the_consolidation_range(levels_file):
    rows = _base_rows()
    range_high = max(r["high"] for r in rows[-10:])
    range_low = min(r["low"] for r in rows[-10:])
    rows.append(dict(open=range_high + 0.1, high=range_high + 1.5, low=range_high, close=range_high + 1.4, volume=300.0))
    data = _candles(rows)
    strategy = _make(levels_file)

    signal = strategy.generate_signal(data)
    sl = strategy.stop_loss_price(data, signal)

    assert sl < range_low


def test_no_volume_column_does_not_block_the_signal(levels_file):
    rows = _base_rows()
    for r in rows:
        del r["volume"]
    range_high = max(r["high"] for r in rows[-10:])
    rows.append(dict(open=range_high + 0.1, high=range_high + 1.5, low=range_high, close=range_high + 1.4))
    data = _candles(rows)
    strategy = _make(levels_file)

    assert strategy.generate_signal(data) == Signal.BUY


def test_sl_price_raises_when_requested_signal_does_not_match_setup(levels_file):
    rows = _base_rows()
    range_high = max(r["high"] for r in rows[-10:])
    rows.append(dict(open=range_high + 0.1, high=range_high + 1.5, low=range_high, close=range_high + 1.4, volume=300.0))
    data = _candles(rows)
    strategy = _make(levels_file)

    with pytest.raises(ValueError):
        strategy.stop_loss_price(data, Signal.SELL)
