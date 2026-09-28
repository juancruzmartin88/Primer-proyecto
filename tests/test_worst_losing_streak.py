from src.backtester import BacktestResult


def _trade(pnl: float) -> dict:
    return {"pnl": pnl}


def test_worst_losing_streak_with_no_trades():
    result = BacktestResult(trades=[])

    streak = result.worst_losing_streak

    assert streak == {"count": 0, "amount": 0.0}


def test_worst_losing_streak_picks_the_deepest_run_by_dollars_not_count():
    trades = [
        _trade(-5), _trade(-5), _trade(-5),  # racha de 3, -15 total
        _trade(50),  # gana, corta la racha
        _trade(-40), _trade(-40),  # racha de 2, -80 total (mas profunda en $)
        _trade(10),
    ]
    result = BacktestResult(trades=trades)

    streak = result.worst_losing_streak

    assert streak == {"count": 2, "amount": -80.0}


def test_worst_losing_streak_running_at_the_end_of_the_list():
    trades = [_trade(20), _trade(-10), _trade(-10), _trade(-10)]
    result = BacktestResult(trades=trades)

    streak = result.worst_losing_streak

    assert streak == {"count": 3, "amount": -30.0}


def test_worst_losing_streak_zero_pnl_does_not_break_the_streak():
    trades = [_trade(-10), _trade(0), _trade(-10)]
    result = BacktestResult(trades=trades)

    streak = result.worst_losing_streak

    # el 0 no es una ganancia (no corta la racha) ni una perdida (no suma) -
    # las dos operaciones de -10 se cuentan como una sola racha de 2.
    assert streak == {"count": 2, "amount": -20.0}
