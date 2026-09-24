"""Dispara un mail de prueba con la configuracion SMTP del .env real.

Sirve para confirmar que las credenciales de Gmail (Contraseña de
aplicacion) funcionan sin tener que esperar a que el bot abra o cierre una
operacion real. No toca el bot ni MT5 - solo intenta enviar un mail.

Uso (con el entorno virtual activado):
    python -m scripts.test_email
"""
from __future__ import annotations

import sys

from src.config import ConfigError, load_config
from src.notifier import EmailConfig, EmailNotifier


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Error de configuracion: {exc}")
        return 1

    if not config.enable_email_notifications:
        print(
            "ENABLE_EMAIL_NOTIFICATIONS esta en false en tu .env - no hay nada que probar. "
            "Poné ENABLE_EMAIL_NOTIFICATIONS=true y volvé a correr este script."
        )
        return 1

    notifier = EmailNotifier(
        EmailConfig(
            smtp_host=config.smtp_host,
            smtp_port=config.smtp_port,
            smtp_user=config.smtp_user,
            smtp_password=config.smtp_password,
            to_email=config.notify_to_email,
        )
    )

    print(f"Enviando mail de prueba a {config.notify_to_email} via {config.smtp_host}:{config.smtp_port}...")
    notifier.notify_error(
        context="Prueba manual",
        message=(
            "Si estas leyendo esto, la configuracion de notificaciones por mail "
            "del bot funciona correctamente. Este mail no indica ningun error real."
        ),
    )
    print("Listo. Revisa tu bandeja de entrada (y la de spam, por las dudas).")
    print("Si NO te llego nada, revisa la salida de arriba - un fallo de SMTP queda logueado ahi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
