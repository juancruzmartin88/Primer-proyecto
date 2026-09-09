"""Configuracion centralizada de logging con loguru.

Todo lo que el bot hace (senales, ordenes, rechazos por riesgo) queda
en logs/bot.log con rotacion diaria, ademas de la consola. Para un bot
que opera plata real, tener trazabilidad completa no es opcional.
"""
from __future__ import annotations

import sys

from loguru import logger


def setup_logging(log_dir: str = "logs") -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=True)
    logger.add(
        f"{log_dir}/bot.log",
        rotation="00:00",
        retention="90 days",
        level="DEBUG",
        encoding="utf-8",
    )
