"""Carga y validacion de la configuracion del bot desde variables de entorno.

Toda credencial y parametro de riesgo vive en variables de entorno (.env),
nunca hardcodeado en el codigo. Ver .env.example para el listado completo.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

_LIVE_CONFIRMATION_VALUE = "ENTIENDO_EL_RIESGO"


class ConfigError(Exception):
    """Error de configuracion: falta una variable o tiene un valor invalido."""


def _get_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"Falta la variable de entorno obligatoria: {name}")
    return value


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"La variable {name} debe ser numerica, recibi: {raw!r}") from exc


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"La variable {name} debe ser entera, recibi: {raw!r}") from exc


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "si"}


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade_pct: float
    max_daily_loss_pct: float
    max_open_positions: int


@dataclass(frozen=True)
class MT5Config:
    login: int
    password: str
    server: str
    path: str | None


@dataclass(frozen=True)
class AppConfig:
    mt5: MT5Config
    risk: RiskConfig
    dry_run: bool
    live_trading_confirmed: bool
    # Limite de tiempo maximo (seccion 6.1, 17/09/2026): APAGADO por
    # defecto. El backtest sobre 7 meses de BTC (17/09/2026) mostro que
    # forzar el cierre a las 4/8/12/24hs empeora el profit factor entre
    # 18% y 45% frente a no tener ningun limite (corta operaciones lentas
    # que igual iban camino al TP) - se dejo el codigo listo en
    # `src/time_exit.py` por si en el futuro cambian las condiciones, pero
    # no se activa sin revalidar. Ver CLAUDE.md para el detalle completo.
    enable_time_exit: bool

    @property
    def is_real_account_server(self) -> bool:
        """Heuristica simple: los servidores demo de Exness incluyen 'Trial' o 'Demo'."""
        server_lower = self.mt5.server.lower()
        return "demo" not in server_lower and "trial" not in server_lower

    def assert_safe_to_trade_live(self) -> None:
        """Traba de seguridad: solo permite operar en cuenta real si TODO coincide.

        Se exige explicitamente:
        - DRY_RUN=false
        - LIVE_TRADING_CONFIRMATION=ENTIENDO_EL_RIESGO
        Esto evita que un .env mal copiado o una variable vacia dispare
        ordenes reales por accidente.
        """
        if self.dry_run:
            return
        if self.is_real_account_server and not self.live_trading_confirmed:
            raise ConfigError(
                "Estas apuntando a una cuenta REAL con DRY_RUN=false pero sin "
                f"confirmar el riesgo. Setea LIVE_TRADING_CONFIRMATION={_LIVE_CONFIRMATION_VALUE} "
                "en tu .env solo cuando hayas validado el bot en demo."
            )


def load_config() -> AppConfig:
    mt5_config = MT5Config(
        login=int(_get_required("MT5_LOGIN")),
        password=_get_required("MT5_PASSWORD"),
        server=_get_required("MT5_SERVER"),
        path=os.getenv("MT5_PATH") or None,
    )
    risk_config = RiskConfig(
        risk_per_trade_pct=_get_float("RISK_PER_TRADE_PCT", 1.0),
        max_daily_loss_pct=_get_float("MAX_DAILY_LOSS_PCT", 3.0),
        max_open_positions=_get_int("MAX_OPEN_POSITIONS", 1),
    )
    live_confirmed = os.getenv("LIVE_TRADING_CONFIRMATION", "") == _LIVE_CONFIRMATION_VALUE

    config = AppConfig(
        mt5=mt5_config,
        risk=risk_config,
        dry_run=_get_bool("DRY_RUN", True),
        live_trading_confirmed=live_confirmed,
        enable_time_exit=_get_bool("ENABLE_TIME_EXIT", False),
    )
    config.assert_safe_to_trade_live()
    return config
