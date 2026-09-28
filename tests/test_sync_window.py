import json

import pandas as pd
import pytest

from src.strategies.sync_window import SyncWindowStrategy
from src.types import Signal


def _make(symbol: str, levels_file, *, sync_window: int, **overrides):
    params = dict(
        symbol=symbol,
        timeframe="H1",
        levels_path=levels_file,
        extreme_lookback=10,
        rsi_oversold=30.0,
        rsi_overbought=70.0,
        sync_window=sync_window,
    )
    params.update(overrides)
    return SyncWindowStrategy(**params)


@pytest.fixture
def levels_file(tmp_path):
    path = tmp_path / "levels.json"
    path.write_text(json.dumps({}))
    return path


def test_accepts_rejection_candle_exactly_at_the_touch(levels_file):
    strategy = _make("X", levels_file, sync_window=2)
    rsi_series = pd.Series([50, 50, 50, 25.0, 32, 40, 55, 60, 50])

    assert strategy._rsi_extreme_and_turn(rsi_series, rejection_idx=3, confirmation_idx=4, direction=Signal.BUY)


def test_accepts_rejection_candle_within_the_sync_window(levels_file):
    strategy = _make("X", levels_file, sync_window=2)
    rsi_series = pd.Series([50, 50, 50, 25.0, 32, 40, 55, 60, 50])

    # Toque en el indice 3, vela de rechazo 2 velas despues (indice 5) - el
    # RSI de confirmacion (indice 6, 55.0) esta bien recuperado, pero aca
    # eso ya no importa - lo unico que se exige es la cercania al toque.
    assert strategy._rsi_extreme_and_turn(rsi_series, rejection_idx=5, confirmation_idx=6, direction=Signal.BUY)


def test_rejects_rejection_candle_beyond_the_sync_window(levels_file):
    strategy = _make("X", levels_file, sync_window=2)
    rsi_series = pd.Series([50, 50, 50, 25.0, 32, 40, 55, 60, 50])

    # Mismo toque en el indice 3, pero la vela de rechazo aparece 3 velas
    # despues (indice 6) - fuera de la ventana de sincronizacion de 2.
    assert not strategy._rsi_extreme_and_turn(rsi_series, rejection_idx=6, confirmation_idx=7, direction=Signal.BUY)


def test_wider_sync_window_accepts_what_the_narrower_one_rejects(levels_file):
    rsi_series = pd.Series([50, 50, 50, 25.0, 32, 40, 55, 60, 50])
    narrow = _make("X", levels_file, sync_window=2)
    wide = _make("X", levels_file, sync_window=3)

    assert not narrow._rsi_extreme_and_turn(rsi_series, rejection_idx=6, confirmation_idx=7, direction=Signal.BUY)
    assert wide._rsi_extreme_and_turn(rsi_series, rejection_idx=6, confirmation_idx=7, direction=Signal.BUY)


def test_does_not_require_rsi_to_have_already_recrossed_the_threshold(levels_file):
    # Diferencia clave con StructuralPullbackStrategy: el RSI de la vela de
    # confirmacion sigue del lado extremo (28.0, todavia <=30) y aun asi
    # se acepta, porque la vela de rechazo esta a solo 1 vela del toque.
    strategy = _make("X", levels_file, sync_window=2)
    rsi_series = pd.Series([50, 50, 25.0, 27.0, 28.0])

    assert strategy._rsi_extreme_and_turn(rsi_series, rejection_idx=3, confirmation_idx=4, direction=Signal.BUY)


def test_no_signal_when_rsi_never_touched_extreme_in_the_lookback(levels_file):
    strategy = _make("X", levels_file, sync_window=3)
    rsi_series = pd.Series([50.0] * 10)

    assert not strategy._rsi_extreme_and_turn(rsi_series, rejection_idx=8, confirmation_idx=9, direction=Signal.BUY)


def test_sell_direction_mirrors_buy(levels_file):
    strategy = _make("X", levels_file, sync_window=2)
    rsi_series = pd.Series([50, 50, 50, 75.0, 68, 60, 45, 40, 50])

    assert strategy._rsi_extreme_and_turn(rsi_series, rejection_idx=5, confirmation_idx=6, direction=Signal.SELL)
    assert not strategy._rsi_extreme_and_turn(rsi_series, rejection_idx=6, confirmation_idx=7, direction=Signal.SELL)
