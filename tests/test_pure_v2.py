import json

import pandas as pd
import pytest

from src.indicators import atr
from src.strategies.pure_v2 import PureV2Strategy
from src.strategies.structural_pullback import StructuralPullbackStrategy
from src.types import Signal


@pytest.fixture
def levels_file(tmp_path):
    path = tmp_path / "levels.json"
    path.write_text(json.dumps({"BUYSYM": [100.0], "SELLSYM": [200.0]}))
    return path


def _make(cls, symbol: str, levels_file, **overrides):
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
        rsi_oversold=30.0,
        rsi_overbought=70.0,
    )
    params.update(overrides)
    return cls(**params)


def _candles(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["time"] = pd.date_range("2024-01-01", periods=len(df), freq="1h")
    return df


def _buy_rows() -> list[dict]:
    # RSI(3) toca sobreventa real en los cierres 111/109/106/101 y ya esta
    # recuperado (>30) para el cierre de la propia vela de rechazo (103.0) -
    # verificado numericamente. La vela de rechazo (ultima fila) es un
    # martillo (mecha inferior >>1.5x cuerpo, mecha superior chica) que
    # ademas toca el nivel 100.0 (low 99.5, dentro de la proximidad de ATR).
    pad = [dict(open=113.0, high=113.0, low=113.0, close=113.0)] * 9
    return pad + [
        dict(open=113.0, high=113.1, low=110.9, close=111.0),
        dict(open=111.0, high=111.1, low=108.9, close=109.0),
        dict(open=109.0, high=109.1, low=105.9, close=106.0),
        dict(open=106.0, high=106.1, low=100.3, close=101.0),
        dict(open=101.0, high=101.6, low=100.8, close=101.5),
        dict(open=101.5, high=102.3, low=101.4, close=102.2),
        dict(open=102.95, high=103.1, low=99.5, close=103.0),  # rechazo
    ]


def _buy_rows_with_deeper_low_in_window() -> list[dict]:
    # Mismo tipo de setup que _buy_rows, pero con una vela DENTRO de la
    # ventana de 5 velas de pullback (no la de rechazo) que perfora mucho
    # mas abajo (low=90.0) que la vela de rechazo (low=99.5). Sirve para
    # distinguir el SL "puro" (solo la vela de rechazo) del SL de la
    # estrategia base (minimo de toda la ventana).
    pad = [dict(open=113.0, high=113.0, low=113.0, close=113.0)] * 9
    return pad + [
        dict(open=113.0, high=113.1, low=90.0, close=111.0),  # low profundo, lejos
        dict(open=111.0, high=111.1, low=108.9, close=109.0),
        dict(open=109.0, high=109.1, low=105.9, close=106.0),
        dict(open=106.0, high=106.1, low=100.3, close=101.0),
        dict(open=101.0, high=101.6, low=100.8, close=101.5),
        dict(open=102.95, high=103.1, low=99.5, close=103.0),  # rechazo
    ]


def _sell_rows() -> list[dict]:
    pad = [dict(open=187.0, high=187.0, low=187.0, close=187.0)] * 9
    return pad + [
        dict(open=187.0, high=210.0, low=186.9, close=189.0),
        dict(open=189.0, high=191.1, low=188.9, close=191.0),
        dict(open=191.0, high=194.1, low=190.9, close=194.0),
        dict(open=194.0, high=199.7, low=193.9, close=199.0),
        dict(open=199.0, high=199.2, low=198.4, close=198.5),
        dict(open=197.05, high=200.5, low=196.9, close=197.0),  # rechazo
    ]


def test_buy_fires_without_a_separate_confirmation_candle(levels_file):
    data = _candles(_buy_rows())
    pure = _make(PureV2Strategy, "BUYSYM", levels_file)
    base = _make(StructuralPullbackStrategy, "BUYSYM", levels_file)

    assert pure.generate_signal(data) == Signal.BUY
    # La estrategia base, sobre la misma serie (la ultima vela es la de
    # rechazo, sin ninguna vela de confirmacion despues), no encuentra
    # setup - necesita una vela mas.
    assert base.generate_signal(data) == Signal.HOLD


def test_sell_fires_without_a_separate_confirmation_candle(levels_file):
    data = _candles(_sell_rows())
    pure = _make(PureV2Strategy, "SELLSYM", levels_file)
    base = _make(StructuralPullbackStrategy, "SELLSYM", levels_file)

    assert pure.generate_signal(data) == Signal.SELL
    assert base.generate_signal(data) == Signal.HOLD


def test_sl_uses_only_rejection_candle_not_full_pullback_window(levels_file):
    data = _candles(_buy_rows_with_deeper_low_in_window())
    pure = _make(PureV2Strategy, "BUYSYM", levels_file)

    signal = pure.generate_signal(data)
    assert signal == Signal.BUY

    pure_sl = pure.stop_loss_price(data, signal)

    rejection_idx = len(data) - 1
    pullback_window = data.iloc[rejection_idx - pure.lookback_candles : rejection_idx + 1]
    current_atr = atr(data, period=pure.atr_period).iloc[-1]
    # Metodo heredado de StructuralPullbackStrategy, no usado por
    # PureV2Strategy pero si por la version del bot en produccion - lo
    # reusamos aca solo para tener el punto de comparacion exacto.
    window_based_sl = pure._calculate_stop_loss(pullback_window, data.iloc[-1], Signal.BUY, current_atr)

    # El SL "puro" ignora el low profundo de una vela anterior en la
    # ventana -> queda mas ajustado (mas alto) que el SL basado en toda la
    # ventana de pullback.
    assert pure_sl > window_based_sl
    assert pure_sl == pytest.approx(
        data["low"].iloc[-1] - pure.sl_atr_margin_mult * current_atr, rel=1e-6
    )


def test_sl_price_raises_when_requested_signal_does_not_match_setup(levels_file):
    data = _candles(_buy_rows())
    pure = _make(PureV2Strategy, "BUYSYM", levels_file)

    with pytest.raises(ValueError):
        pure.stop_loss_price(data, Signal.SELL)
