import json

import pandas as pd

from src.levels import (
    detect_fractal_levels,
    get_levels_for_symbol,
    load_manual_levels,
    nearest_level_beyond_price,
    nearest_level_touched,
)


def test_load_manual_levels_reads_symbol_entry(tmp_path):
    levels_file = tmp_path / "levels.json"
    levels_file.write_text(json.dumps({"XAUUSD": [2350.0, 2400.5, 2300.0]}))

    levels = load_manual_levels("XAUUSD", levels_file)

    assert levels == [2300.0, 2350.0, 2400.5]  # ordenados


def test_load_manual_levels_missing_file_returns_empty(tmp_path):
    assert load_manual_levels("XAUUSD", tmp_path / "no_existe.json") == []


def test_load_manual_levels_missing_symbol_returns_empty(tmp_path):
    levels_file = tmp_path / "levels.json"
    levels_file.write_text(json.dumps({"BTCUSD": [60000]}))

    assert load_manual_levels("XAUUSD", levels_file) == []


def _sample_ohlc_with_spike() -> pd.DataFrame:
    highs = [100, 101, 102, 105, 102, 101, 100, 99, 98]
    lows = [100, 99, 98, 95, 98, 99, 100, 101, 102]
    return pd.DataFrame({"high": highs, "low": lows, "close": highs})


def test_detect_fractal_levels_finds_local_peak_and_trough():
    data = _sample_ohlc_with_spike()
    levels = detect_fractal_levels(data, window=2)
    assert 105.0 in levels
    assert 95.0 in levels


def test_get_levels_for_symbol_combines_manual_and_fractal(tmp_path):
    # Desde el 22/09/2026 ya no es "manual O fractal" - se combinan los
    # dos siempre, para que un nivel manual desactualizado no deje al bot
    # ciego (ver docstring de src/levels.py, incidente real de BTC).
    levels_file = tmp_path / "levels.json"
    levels_file.write_text(json.dumps({"XAUUSD": [2000.0]}))
    data = _sample_ohlc_with_spike()

    levels = get_levels_for_symbol("XAUUSD", data, manual_levels_path=levels_file)

    assert 2000.0 in levels  # el manual sigue presente
    assert 105.0 in levels  # y el fractal tambien, no se pisan
    assert 95.0 in levels


def test_get_levels_for_symbol_falls_back_to_fractal_when_no_manual(tmp_path):
    levels_file = tmp_path / "levels.json"
    levels_file.write_text(json.dumps({"BTCUSD": [60000]}))  # otro simbolo
    data = _sample_ohlc_with_spike()

    levels = get_levels_for_symbol("XAUUSD", data, manual_levels_path=levels_file)

    assert 105.0 in levels
    assert 95.0 in levels


def test_nearest_level_beyond_price_up_and_down():
    levels = [95.0, 100.0, 105.0, 110.0]
    assert nearest_level_beyond_price(levels, price=101.0, direction="up") == 105.0
    assert nearest_level_beyond_price(levels, price=101.0, direction="down") == 100.0
    assert nearest_level_beyond_price(levels, price=200.0, direction="up") is None


def test_nearest_level_touched_within_proximity():
    levels = [100.0, 200.0]
    assert nearest_level_touched(levels, price=100.4, proximity=0.5) == 100.0
    assert nearest_level_touched(levels, price=150.0, proximity=0.5) is None
