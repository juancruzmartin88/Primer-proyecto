"""Notificaciones por mail (24/09/2026).

Avisa por mail cuando el bot abre o cierra una operacion real, o si
encuentra un error inesperado - sin que el usuario tenga que revisar
`logs/bot.log` a cada rato para saber si el bot sigue vivo. Surgio de un
tramo real de 6.5hs sin ninguna operacion (24/09/2026) que generaba
desconfianza aunque el bot estuviera funcionando bien - ver CLAUDE.md,
seccion "Timeframe M30 para BTC". No cambia la frecuencia real de
operaciones, solo la visibilidad.

Usa SMTP simple, pensado por defecto para Gmail (`smtp.gmail.com:587` con
STARTTLS) - con Gmail hace falta generar una "Contraseña de aplicacion" en
la cuenta (no la contraseña normal de la cuenta), ver README.

Deliberadamente NO se notifica cada bloqueo por gestion de riesgo (seria
un mail cada 30 segundos mientras haya una posicion manual abierta, como
paso el 22-24/09/2026) - solo aperturas, cierres, y errores genuinos.
"""
from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.mime.text import MIMEText

from loguru import logger

from src.mt5_client import ClosedTradeInfo
from src.types import Signal


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    to_email: str


class EmailNotifier:
    def __init__(self, config: EmailConfig) -> None:
        self.config = config

    def _send(self, subject: str, body: str) -> None:
        # Un fallo de mail nunca tiene que tirar abajo el loop del bot - el
        # trading sigue funcionando igual aunque el aviso no llegue, solo
        # queda logueado el error para diagnosticar despues.
        try:
            message = MIMEText(body, "plain", "utf-8")
            message["Subject"] = subject
            message["From"] = self.config.smtp_user
            message["To"] = self.config.to_email
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=15) as server:
                server.starttls()
                server.login(self.config.smtp_user, self.config.smtp_password)
                server.sendmail(self.config.smtp_user, [self.config.to_email], message.as_string())
            logger.info("Notificacion enviada por mail: {}", subject)
        except Exception:
            logger.exception("No se pudo enviar la notificacion por mail (subject={!r}).", subject)

    def notify_trade_opened(
        self,
        *,
        symbol: str,
        signal: Signal,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        volume: float,
        dry_run: bool,
    ) -> None:
        tag = "[SIMULADO] " if dry_run else ""
        subject = f"{tag}Bot: {symbol} - {signal.value} abierta a {entry_price:.2f}"
        body = (
            f"{tag}Se abrio una operacion {signal.value} en {symbol}.\n\n"
            f"Entrada: {entry_price:.2f}\n"
            f"Stop Loss: {stop_loss:.2f}\n"
            f"Take Profit: {take_profit:.2f}\n"
            f"Volumen: {volume} lotes\n"
        )
        self._send(subject, body)

    def notify_trade_closed(self, *, symbol: str, ticket: int, info: ClosedTradeInfo | None) -> None:
        if info is None:
            subject = f"Bot: {symbol} - operacion #{ticket} cerrada (sin detalle disponible)"
            body = (
                f"El bot detecto que la posicion #{ticket} de {symbol} ya no esta abierta, "
                "pero no pudo recuperar el detalle del cierre desde el historial de MT5. "
                "Revisa el historial de la cuenta para confirmar el resultado."
            )
            self._send(subject, body)
            return
        result_word = "ganancia" if info.profit >= 0 else "perdida"
        subject = f"Bot: {symbol} - operacion cerrada, {result_word} ${info.profit:.2f}"
        body = (
            f"Se cerro la operacion #{ticket} en {symbol}.\n\n"
            f"Resultado: {result_word} de ${info.profit:.2f}\n"
            f"Precio de cierre: {info.exit_price:.2f}\n"
            f"Hora de cierre: {info.exit_time}\n"
        )
        self._send(subject, body)

    def notify_error(self, *, context: str, message: str) -> None:
        subject = f"Bot: error inesperado ({context})"
        body = f"El bot encontro un error inesperado en {context}:\n\n{message}"
        self._send(subject, body)
