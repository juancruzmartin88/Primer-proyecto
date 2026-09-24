from src.mt5_client import ClosedTradeInfo
from src.notifier import EmailConfig, EmailNotifier
from src.types import Signal


def _make_notifier() -> tuple[EmailNotifier, list[tuple[str, str]]]:
    notifier = EmailNotifier(
        EmailConfig(
            smtp_host="smtp.gmail.com", smtp_port=587,
            smtp_user="bot@gmail.com", smtp_password="app-password",
            to_email="juan@gmail.com",
        )
    )
    sent: list[tuple[str, str]] = []
    notifier._send = lambda subject, body: sent.append((subject, body))  # type: ignore[method-assign]
    return notifier, sent


def test_notify_trade_opened_real_order_has_no_simulado_tag():
    notifier, sent = _make_notifier()

    notifier.notify_trade_opened(
        symbol="BTCUSDm", signal=Signal.BUY, entry_price=80123.45, stop_loss=79000.0,
        take_profit=82000.0, volume=0.02, dry_run=False,
    )

    assert len(sent) == 1
    subject, body = sent[0]
    assert "[SIMULADO]" not in subject
    assert "BTCUSDm" in subject
    assert "BUY" in subject
    assert "79000.00" in body
    assert "82000.00" in body
    assert "0.02" in body


def test_notify_trade_opened_dry_run_is_tagged_simulado():
    notifier, sent = _make_notifier()

    notifier.notify_trade_opened(
        symbol="XAUUSDm", signal=Signal.SELL, entry_price=4300.0, stop_loss=4310.0,
        take_profit=4280.0, volume=0.01, dry_run=True,
    )

    subject, body = sent[0]
    assert "[SIMULADO]" in subject
    assert "[SIMULADO]" in body


def test_notify_trade_closed_with_profit_says_ganancia():
    notifier, sent = _make_notifier()
    info = ClosedTradeInfo(ticket=111, symbol="BTCUSDm", profit=27.98, exit_price=84604.05, exit_time="2026-09-23T14:00:00Z")

    notifier.notify_trade_closed(symbol="BTCUSDm", ticket=111, info=info)

    subject, body = sent[0]
    assert "ganancia" in subject
    assert "27.98" in subject


def test_notify_trade_closed_with_loss_says_perdida():
    notifier, sent = _make_notifier()
    info = ClosedTradeInfo(ticket=222, symbol="XAUUSDm", profit=-11.87, exit_price=4092.35, exit_time="2026-09-22T09:00:00Z")

    notifier.notify_trade_closed(symbol="XAUUSDm", ticket=222, info=info)

    subject, body = sent[0]
    assert "perdida" in subject
    assert "-11.87" in subject


def test_notify_trade_closed_without_info_still_sends_a_notice():
    notifier, sent = _make_notifier()

    notifier.notify_trade_closed(symbol="BTCUSDm", ticket=333, info=None)

    assert len(sent) == 1
    subject, body = sent[0]
    assert "333" in subject
    assert "sin detalle disponible" in subject


def test_notify_error_includes_context_and_message():
    notifier, sent = _make_notifier()

    notifier.notify_error(context="BTCUSDm", message="MT5ConnectionError: no se pudo obtener el precio")

    subject, body = sent[0]
    assert "BTCUSDm" in subject
    assert "MT5ConnectionError" in body
