import pandas as pd
import pytest

from src.strategies.breakout import BreakoutStrategy
from src.types import Signal


def _make_strategy(**overrides) -> BreakoutStrategy:
    # Periodos chicos (atr_period=3, ventanas 5/10 en vez de 14/50) para que
    # el setup se pueda armar con pocas velas y sea facil de verificar a
    # mano/numericamente - la logica es la misma que en produccion.
    params = dict(
        symbol="TEST",
        timeframe="H1",
        atr_period=3,
        consolidation_short_window=5,
        consolidation_long_window=10,
        volume_ma_period=5,
        volume_breakout_mult=1.0,
        min_risk_reward=2.0,
    )
    params.update(overrides)
    return BreakoutStrategy(**params)


def _to_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["time"] = pd.date_range("2024-01-01", periods=len(df), freq="1h")
    return df


def _buy_rows(*, confirmation_close: float = 124.0) -> list[dict]:
    # 13 velas planas (padding) + 5 velas anchas (suben el ATR base) + 5
    # velas angostas (consolidacion: ATR reciente cae por debajo de su
    # propio promedio de base) + vela de ruptura (cierra por encima del
    # rango 119.7-120.8) + vela de confirmacion. Verificado numericamente
    # (ver ATR(3) de cada tramo en el historial de este archivo).
    rows = [dict(open=100.0, high=100.0, low=100.0, close=100.0)] * 13
    rows += [
        dict(open=100.0, high=106.0, low=99.0, close=104.0),
        dict(open=104.0, high=110.0, low=103.0, close=108.0),
        dict(open=108.0, high=114.0, low=107.0, close=112.0),
        dict(open=112.0, high=118.0, low=111.0, close=116.0),
        dict(open=116.0, high=122.0, low=115.0, close=120.0),
    ]
    rows += [
        dict(open=120.0, high=120.6, low=119.7, close=120.3),
        dict(open=120.3, high=120.7, low=120.0, close=120.4),
        dict(open=120.4, high=120.8, low=120.1, close=120.5),
        dict(open=120.5, high=120.7, low=120.2, close=120.4),
        dict(open=120.4, high=120.6, low=120.1, close=120.3),
    ]
    rows.append(dict(open=120.3, high=123.2, low=120.2, close=123.0))  # ruptura
    rows.append(dict(open=123.0, high=124.5, low=122.8, close=confirmation_close))  # confirmacion
    return rows


def _sell_rows(*, confirmation_close: float = 76.0) -> list[dict]:
    # Espejo del caso BUY: consolidacion en 79.2-80.3, ruptura bajista.
    rows = [dict(open=100.0, high=100.0, low=100.0, close=100.0)] * 13
    rows += [
        dict(open=100.0, high=101.0, low=94.0, close=96.0),
        dict(open=96.0, high=97.0, low=90.0, close=92.0),
        dict(open=92.0, high=93.0, low=86.0, close=88.0),
        dict(open=88.0, high=89.0, low=82.0, close=84.0),
        dict(open=84.0, high=85.0, low=78.0, close=80.0),
    ]
    rows += [
        dict(open=80.0, high=80.3, low=79.4, close=79.7),
        dict(open=79.7, high=80.0, low=79.3, close=79.6),
        dict(open=79.6, high=79.9, low=79.2, close=79.5),
        dict(open=79.5, high=79.8, low=79.3, close=79.6),
        dict(open=79.6, high=79.9, low=79.4, close=79.7),
    ]
    rows.append(dict(open=79.7, high=79.8, low=76.8, close=77.0))  # ruptura
    rows.append(dict(open=77.0, high=77.2, low=75.5, close=confirmation_close))  # confirmacion
    return rows


def test_buy_setup_detected_on_upside_breakout():
    strategy = _make_strategy()
    data = _to_df(_buy_rows())

    signal = strategy.generate_signal(data)

    assert signal == Signal.BUY
    sl = strategy.stop_loss_price(data, signal)
    tp = strategy.take_profit_price(data, signal)
    entry = data["close"].iloc[-1]
    assert sl == pytest.approx(119.7)  # borde opuesto del rango roto (minimo)
    assert tp == pytest.approx(entry + 2.0 * (entry - sl))  # TP a 2R


def test_sell_setup_detected_on_downside_breakout():
    strategy = _make_strategy()
    data = _to_df(_sell_rows())

    signal = strategy.generate_signal(data)

    assert signal == Signal.SELL
    sl = strategy.stop_loss_price(data, signal)
    tp = strategy.take_profit_price(data, signal)
    entry = data["close"].iloc[-1]
    assert sl == pytest.approx(80.3)  # borde opuesto del rango roto (maximo)
    assert tp == pytest.approx(entry - 2.0 * (sl - entry))  # TP a 2R


def test_no_setup_when_confirmation_invalidates_the_broken_range():
    # La vela de confirmacion tiene que seguir cerrando por fuera del rango
    # roto (119.7-120.8). Si cierra adentro (120.5), invalida la ruptura.
    strategy = _make_strategy()
    data = _to_df(_buy_rows(confirmation_close=120.5))

    assert strategy.generate_signal(data) == Signal.HOLD


def test_no_setup_when_not_consolidating_before_breakout():
    # Si las velas previas a la ruptura siguen igual de anchas que la base
    # (sin compresion de ATR), no hay "rango" que romper - HOLD aunque la
    # ultima vela cierre mas alto que las anteriores.
    rows = [dict(open=100.0, high=100.0, low=100.0, close=100.0)] * 13
    rows += [
        dict(open=100.0, high=106.0, low=99.0, close=104.0),
        dict(open=104.0, high=110.0, low=103.0, close=108.0),
        dict(open=108.0, high=114.0, low=107.0, close=112.0),
        dict(open=112.0, high=118.0, low=111.0, close=116.0),
        dict(open=116.0, high=122.0, low=115.0, close=120.0),
    ]
    rows += [
        dict(open=120.0, high=126.0, low=119.0, close=124.0),
        dict(open=124.0, high=130.0, low=123.0, close=128.0),
        dict(open=128.0, high=134.0, low=127.0, close=132.0),
        dict(open=132.0, high=138.0, low=131.0, close=136.0),
        dict(open=136.0, high=142.0, low=135.0, close=140.0),
    ]
    rows.append(dict(open=140.0, high=146.0, low=139.0, close=144.0))
    rows.append(dict(open=144.0, high=150.0, low=143.0, close=148.0))
    strategy = _make_strategy()
    data = _to_df(rows)

    assert strategy.generate_signal(data) == Signal.HOLD


def test_no_setup_without_enough_history():
    strategy = _make_strategy()
    data = _to_df(_buy_rows()).tail(10).reset_index(drop=True)

    assert strategy.generate_signal(data) == Signal.HOLD


def test_no_setup_when_volume_is_below_average():
    strategy = _make_strategy()
    data = _to_df(_buy_rows())
    data["tick_volume"] = 100
    data.loc[23, "tick_volume"] = 50  # vela de ruptura con volumen flojo

    assert strategy.generate_signal(data) == Signal.HOLD


def test_setup_detected_with_volume_above_average():
    strategy = _make_strategy()
    data = _to_df(_buy_rows())
    data["tick_volume"] = 100
    data.loc[23, "tick_volume"] = 300  # vela de ruptura con volumen fuerte (>=1.5x)

    assert strategy.generate_signal(data) == Signal.BUY


def test_stop_loss_price_raises_without_prior_signal():
    strategy = _make_strategy()
    data = _to_df(_buy_rows(confirmation_close=120.5))  # invalidado -> HOLD

    with pytest.raises(ValueError):
        strategy.stop_loss_price(data, Signal.BUY)
