from dataclasses import dataclass

from src.bot import _check_position_closed, build_notifier
from src.config import (
    AppConfig,
    MT5Config,
    RiskConfig,
)
from src.mt5_client import ClosedTradeInfo, OpenPosition
from src.types import Signal


def _make_config(**overrides) -> AppConfig:
    defaults = dict(
        mt5=MT5Config(login=1, password="x", server="Exness-MT5Trial1", path=None),
        risk=RiskConfig(risk_per_trade_pct=2.0, max_daily_loss_pct=3.0, max_open_positions=1),
        dry_run=True,
        live_trading_confirmed=False,
        enable_time_exit=False,
        enable_eth=False,
        enable_breakout_strategy=False,
        breakout_bucket_pct=15.0,
        breakout_risk_per_trade_pct=3.0,
        enable_email_notifications=False,
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_user="",
        smtp_password="",
        notify_to_email="",
    )
    defaults.update(overrides)
    return AppConfig(**defaults)


def _position(ticket: int) -> OpenPosition:
    return OpenPosition(
        ticket=ticket,
        symbol="BTCUSDm",
        signal=Signal.BUY,
        volume=0.01,
        price_open=80000.0,
        time_open=None,  # no se usa en estos tests
        stop_loss=79000.0,
        take_profit=82000.0,
    )


@dataclass
class _RecordedNotification:
    symbol: str
    ticket: int
    info: ClosedTradeInfo | None


class _FakeClient:
    def __init__(self, current_position: OpenPosition | None, closed_info: ClosedTradeInfo | None = None):
        self.current_position = current_position
        self.closed_info = closed_info

    def get_open_position_by_bot(self, symbol: str) -> OpenPosition | None:
        return self.current_position

    def get_closed_trade_info(self, ticket: int) -> ClosedTradeInfo | None:
        return self.closed_info


class _FakeNotifier:
    def __init__(self):
        self.closed: list[_RecordedNotification] = []

    def notify_trade_closed(self, *, symbol: str, ticket: int, info):
        self.closed.append(_RecordedNotification(symbol, ticket, info))


def test_no_previous_ticket_just_records_current_without_notifying():
    client = _FakeClient(current_position=_position(111))
    notifier = _FakeNotifier()
    known_tickets: dict[str, int | None] = {}

    _check_position_closed(client, "BTCUSDm", known_tickets, notifier)

    assert known_tickets["BTCUSDm"] == 111
    assert notifier.closed == []


def test_same_ticket_still_open_does_not_notify():
    client = _FakeClient(current_position=_position(111))
    notifier = _FakeNotifier()
    known_tickets = {"BTCUSDm": 111}

    _check_position_closed(client, "BTCUSDm", known_tickets, notifier)

    assert known_tickets["BTCUSDm"] == 111
    assert notifier.closed == []


def test_position_closed_notifies_with_closed_trade_info():
    closed_info = ClosedTradeInfo(
        ticket=111, symbol="BTCUSDm", profit=42.5, exit_price=81000.0, exit_time="2026-09-24T12:00:00Z"
    )
    client = _FakeClient(current_position=None, closed_info=closed_info)
    notifier = _FakeNotifier()
    known_tickets = {"BTCUSDm": 111}

    _check_position_closed(client, "BTCUSDm", known_tickets, notifier)

    assert known_tickets["BTCUSDm"] is None
    assert len(notifier.closed) == 1
    assert notifier.closed[0].ticket == 111
    assert notifier.closed[0].info is closed_info


def test_position_replaced_by_a_new_one_notifies_the_old_ticket_closed():
    # Se cerro la #111 y ya se abrio una nueva (#222) antes de la siguiente
    # vuelta del loop - igual tiene que notificar el cierre de la vieja.
    client = _FakeClient(current_position=_position(222))
    notifier = _FakeNotifier()
    known_tickets = {"BTCUSDm": 111}

    _check_position_closed(client, "BTCUSDm", known_tickets, notifier)

    assert known_tickets["BTCUSDm"] == 222
    assert len(notifier.closed) == 1
    assert notifier.closed[0].ticket == 111


def test_no_notifier_does_not_crash():
    client = _FakeClient(current_position=None)
    known_tickets = {"BTCUSDm": 111}

    _check_position_closed(client, "BTCUSDm", known_tickets, None)

    assert known_tickets["BTCUSDm"] is None


def test_build_notifier_returns_none_when_disabled():
    config = _make_config(enable_email_notifications=False)
    assert build_notifier(config) is None


def test_build_notifier_builds_configured_notifier_when_enabled():
    config = _make_config(
        enable_email_notifications=True,
        smtp_user="bot@gmail.com",
        smtp_password="app-password",
        notify_to_email="juan@gmail.com",
    )
    notifier = build_notifier(config)
    assert notifier is not None
    assert notifier.config.smtp_user == "bot@gmail.com"
    assert notifier.config.to_email == "juan@gmail.com"
