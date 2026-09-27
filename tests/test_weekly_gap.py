import pandas as pd

from src.types import Signal
from src.weekly_gap import find_reopen_indices, simulate_straddle, summarize


def _candle(time, o, h, l, c):
    return {"time": pd.Timestamp(time), "open": o, "high": h, "low": l, "close": c}


def _df(rows):
    return pd.DataFrame(rows)


def test_find_reopen_indices_detects_weekend_gap():
    rows = [
        _candle("2026-09-18 21:00", 100, 101, 99, 100),
        _candle("2026-09-18 22:00", 100, 101, 99, 100),
        # hueco de fin de semana (~46hs, viernes 22:00 -> domingo 20:00)
        _candle("2026-09-20 20:00", 100, 103, 97, 101),
        _candle("2026-09-20 21:00", 101, 102, 100, 101),
    ]
    df = _df(rows)

    reopen_idxs = find_reopen_indices(df, min_gap_hours=20.0)

    assert reopen_idxs == [2]


def test_find_reopen_indices_ignores_normal_hourly_gaps():
    rows = [_candle(f"2026-09-18 {h:02d}:00", 100, 101, 99, 100) for h in range(20, 24)]
    df = _df(rows)

    assert find_reopen_indices(df, min_gap_hours=20.0) == []


def test_simulate_straddle_filters_low_range_reopen_candle():
    rows = [
        _candle("2026-09-20 20:00", 100.0, 100.1, 99.9, 100.0),  # rango 0.2, chico
        _candle("2026-09-20 21:00", 100.0, 105.0, 95.0, 102.0),
    ]
    df = _df(rows)

    result = simulate_straddle(df, reopen_idx=0, current_atr=5.0, min_range_atr_mult=1.0)

    assert result is None


def test_simulate_straddle_buy_side_hits_take_profit():
    rows = [
        _candle("2026-09-20 20:00", 100.0, 110.0, 90.0, 105.0),  # reapertura, rango 20
        _candle("2026-09-20 21:00", 105.0, 111.0, 104.0, 110.0),  # dispara el Buy Stop (110)
        _candle("2026-09-20 22:00", 110.0, 131.0, 109.0, 125.0),  # toca TP (1R = 130)
    ]
    df = _df(rows)

    result = simulate_straddle(df, reopen_idx=0, current_atr=5.0, min_range_atr_mult=1.0, tp_r_multiple=1.0)

    assert result is not None
    assert result.direction == Signal.BUY
    assert result.entry == 110.0
    assert result.stop_loss == 90.0
    assert result.take_profit == 130.0
    assert result.hit == "tp"
    assert result.pnl_r == 1.0


def test_simulate_straddle_sell_side_hits_stop_loss():
    rows = [
        _candle("2026-09-20 20:00", 100.0, 110.0, 90.0, 95.0),  # reapertura, rango 20
        _candle("2026-09-20 21:00", 95.0, 91.0, 88.0, 90.0),  # dispara el Sell Stop (90)
        _candle("2026-09-20 22:00", 90.0, 111.0, 89.0, 109.0),  # revierte y toca el SL (110)
    ]
    df = _df(rows)

    result = simulate_straddle(df, reopen_idx=0, current_atr=5.0, min_range_atr_mult=1.0, tp_r_multiple=1.0)

    assert result is not None
    assert result.direction == Signal.SELL
    assert result.entry == 90.0
    assert result.stop_loss == 110.0
    assert result.hit == "sl"
    assert result.pnl_r == -1.0


def test_simulate_straddle_no_resolution_when_neither_pending_triggers():
    rows = [
        _candle("2026-09-20 20:00", 100.0, 110.0, 90.0, 100.0),
        _candle("2026-09-20 21:00", 100.0, 105.0, 95.0, 100.0),  # nunca rompe 110 ni 90
    ]
    df = _df(rows)

    result = simulate_straddle(df, reopen_idx=0, current_atr=5.0, max_lookahead=1)

    assert result is None


def test_simulate_straddle_both_levels_touched_same_candle_picks_closer_to_open():
    rows = [
        _candle("2026-09-20 20:00", 100.0, 110.0, 90.0, 100.0),
        # vela violenta que toca ambos niveles - el open (108) esta mas
        # cerca del nivel de arriba (110) que del de abajo (90).
        _candle("2026-09-20 21:00", 108.0, 112.0, 85.0, 95.0),
        _candle("2026-09-20 22:00", 95.0, 131.0, 94.0, 125.0),
    ]
    df = _df(rows)

    result = simulate_straddle(df, reopen_idx=0, current_atr=5.0, tp_r_multiple=1.0)

    assert result is not None
    assert result.direction == Signal.BUY


def test_summarize_computes_profit_factor_and_win_rate():
    outcomes = [
        simulate_straddle(
            _df([
                _candle("2026-01-01 00:00", 100.0, 110.0, 90.0, 100.0),
                _candle("2026-01-01 01:00", 105.0, 111.0, 104.0, 110.0),
                _candle("2026-01-01 02:00", 110.0, 131.0, 109.0, 125.0),
            ]),
            reopen_idx=0, current_atr=5.0, tp_r_multiple=1.0,
        ),
        simulate_straddle(
            _df([
                _candle("2026-01-08 00:00", 100.0, 110.0, 90.0, 95.0),
                _candle("2026-01-08 01:00", 95.0, 91.0, 88.0, 90.0),
                _candle("2026-01-08 02:00", 90.0, 111.0, 89.0, 109.0),
            ]),
            reopen_idx=0, current_atr=5.0, tp_r_multiple=1.0,
        ),
    ]

    summary = summarize(outcomes)

    assert summary["trades_resueltos"] == 2
    assert summary["win_rate"] == 0.5
    assert summary["profit_factor"] == 1.0  # +1R y -1R
    assert summary["total_r"] == 0.0
