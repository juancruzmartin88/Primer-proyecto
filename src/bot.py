"""Loop principal del bot en vivo (demo o real, segun configuracion).

Desde el 14/09/2026 opera DOS instrumentos en la misma corrida (BTC + Oro,
cuenta real, ver CLAUDE.md) con la Metodologia v2 de
`src/strategies/structural_pullback.py`. Flujo por instrumento, en cada
vuelta del loop:

  1. Traer velas recientes de MT5.
  2. Pedirle una senal a la estrategia de ese instrumento.
  3. Si hay senal de entrada, validarla contra el RiskManager (kill switch
     diario compartido entre los dos instrumentos, limite de posiciones
     abiertas PROPIO de ese instrumento, sizing).
  4. Enviar la orden (o simularla, si DRY_RUN=true).

Uso:
    python -m src.bot
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
from loguru import logger

from src.config import AppConfig, load_config
from src.indicators import atr, rsi
from src.logger_setup import setup_logging
from src.mt5_client import MT5Client, OpenPosition
from src.risk_manager import RiskLimitExceeded, RiskManager
from src.strategies.structural_pullback import StructuralPullbackStrategy
from src.time_exit import should_force_close
from src.types import Signal, TradeOrder

POLL_INTERVAL_SECONDS = 30

# Sufijo "m": la cuenta demo del usuario (Standard, Exness-MT5Trial11) nombra
# los simbolos asi - verificado en Market Watch el 10/09/2026. LA CUENTA REAL
# PUEDE SER DE OTRO TIPO: antes de correr el bot en real, revisar en su
# Market Watch como se llaman ahi XAUUSD y BTCUSD exactamente y actualizar
# estas dos constantes si hace falta.
XAUUSD_SYMBOL = "XAUUSDm"
BTCUSD_SYMBOL = "BTCUSDm"


def build_strategies() -> list[StructuralPullbackStrategy]:
    # Metodologia v2 (seccion 4 del sistema, 14/09/2026) para los dos
    # instrumentos. El limite dinamico de riesgo de Oro (seccion 3.2: solo
    # tomar señales cuyo SL tecnico entre en el % de riesgo objetivo al lote
    # minimo del broker) no se hardcodea aca - lo aplica RiskManager en cada
    # señal, recalculado sobre el balance real de la cuenta en ese momento.
    return [
        StructuralPullbackStrategy(symbol=BTCUSD_SYMBOL, timeframe="H1"),
        StructuralPullbackStrategy(symbol=XAUUSD_SYMBOL, timeframe="H1"),
    ]


def run() -> None:
    setup_logging()
    config = load_config()
    strategies = build_strategies()

    client = MT5Client(config.mt5)
    risk_manager = RiskManager(config.risk)

    logger.info(
        "Arrancando bot | dry_run={} | simbolos={} | timeframe=H1 | riesgo_por_operacion={}%",
        config.dry_run,
        [s.symbol for s in strategies],
        config.risk.risk_per_trade_pct,
    )
    if not config.dry_run:
        logger.warning("MODO REAL: el bot va a enviar ordenes reales al broker.")

    client.connect()
    for strategy in strategies:
        if strategy.symbol == XAUUSD_SYMBOL:
            logger.info(
                "{}: el bot descarta automaticamente cualquier señal cuyo Stop Loss "
                "tecnico, al lote minimo del broker, fuerce mas del {}% de riesgo real "
                "sobre el balance actual de la cuenta (seccion 3.2 del sistema, "
                "14/09/2026) - no hace falta ningun ajuste manual si cambia el capital.",
                strategy.symbol,
                config.risk.risk_per_trade_pct,
            )
    try:
        while True:
            for strategy in strategies:
                try:
                    iterate(client, strategy, risk_manager, config)
                except RiskLimitExceeded as exc:
                    logger.warning("Operacion bloqueada por gestion de riesgo ({}): {}", strategy.symbol, exc)
                except Exception:
                    logger.exception("Error inesperado en la iteracion del bot ({}).", strategy.symbol)
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Bot detenido manualmente.")
    finally:
        client.disconnect()


def iterate(client: MT5Client, strategy, risk_manager: RiskManager, config: AppConfig) -> None:
    account = client.get_account_info()
    # Kill switch diario: comparte el mismo contador de PnL realizado entre
    # los dos instrumentos (es un limite de cuenta, no por simbolo).
    risk_manager.check_daily_loss_limit(account.balance)

    data = client.get_rates(strategy.symbol, strategy.timeframe)

    # Si el bot ya tiene una posicion propia abierta en este simbolo, esta
    # vuelta del loop se dedica a gestionarla (limite de tiempo, seccion 6.1
    # del sistema, 17/09/2026) en vez de buscar una señal nueva - mientras
    # siga abierta, el limite de posiciones de abajo la bloquearia igual.
    open_position = client.get_open_position_by_bot(strategy.symbol)
    if open_position is not None:
        _manage_open_position(client, strategy, open_position, data, config)
        return

    # Limite de posiciones abiertas: PROPIO de este instrumento (14/09/2026,
    # decision explicita del usuario) - una señal de Oro no se pierde porque
    # BTC tenga una posicion abierta, y viceversa. Cuenta tambien posiciones
    # manuales del usuario en el mismo simbolo (seccion 3, "no abrir una
    # segunda posicion sobre la misma tesis").
    open_positions = client.get_open_positions_count(strategy.symbol)
    risk_manager.check_open_positions_limit(open_positions)

    signal = strategy.generate_signal(data)
    if signal not in (Signal.BUY, Signal.SELL):
        return

    # La vela de confirmacion del setup ya cerro (el bot solo mira velas
    # cerradas) -> la orden siempre es de mercado, nunca pendiente (decision
    # tomada el 14/09/2026: ver docstring de structural_pullback.py).
    entry_price = data["close"].iloc[-1]
    sl_price = strategy.stop_loss_price(data, signal)
    tp_price = strategy.take_profit_price(data, signal)
    specs = client.get_symbol_trade_specs(strategy.symbol)

    size_result = risk_manager.calculate_position_size(
        account_balance=account.balance,
        entry_price=entry_price,
        stop_loss_price=sl_price,
        pip_value_per_lot=specs.pip_value_per_lot,
        pip_size=specs.pip_size,
        min_lot=specs.min_lot,
        lot_step=specs.lot_step,
    )
    # Riesgo real vs. objetivo se verifica ACA, contra los datos que reporta
    # el broker (specs y account.balance) - nunca contra un calculo hecho
    # por separado (seccion 3 del sistema). Bloquea en cuenta real si el
    # lote minimo fuerza mas riesgo del configurado (tipicamente Oro); en
    # demo solo loguea. Esto es lo que impone en la practica el limite de
    # 13 puntos de SL de la seccion 3.2, recalculado solo con el balance
    # real de la cuenta - no un numero fijo en el codigo.
    risk_manager.enforce_min_lot_policy(size_result, is_real_account=config.is_real_account_server)

    order = TradeOrder(
        symbol=strategy.symbol,
        signal=signal,
        volume=size_result.volume,
        stop_loss=sl_price,
        take_profit=tp_price,
    )
    client.send_order(order, dry_run=config.dry_run)


def _manage_open_position(
    client: MT5Client, strategy, position: OpenPosition, data: pd.DataFrame, config: AppConfig
) -> None:
    """Aplica el limite de tiempo maximo (seccion 6.1 del sistema,
    17/09/2026) a una posicion que el bot mismo abrio. No toca posiciones
    manuales del usuario (`get_open_position_by_bot` ya las excluye)."""
    current_price = data["close"].iloc[-1]
    rsi_series = rsi(data["close"], period=strategy.rsi_period)
    atr_series = atr(data, period=strategy.atr_period)
    current_rsi = rsi_series.iloc[-1]
    current_atr = atr_series.iloc[-1]
    if pd.isna(current_rsi) or pd.isna(current_atr):
        return

    now = datetime.now(timezone.utc)
    if not should_force_close(
        direction=position.signal,
        entry_price=position.price_open,
        entry_time=position.time_open,
        current_time=now,
        current_price=current_price,
        current_rsi=current_rsi,
        current_atr=current_atr,
    ):
        return

    hours_open = (now - position.time_open).total_seconds() / 3600.0
    logger.info(
        "{}: cerrando posicion #{} por limite de tiempo (seccion 6.1) - "
        "abierta hace {:.1f}hs sin avance claro hacia TP/SL.",
        strategy.symbol,
        position.ticket,
        hours_open,
    )
    client.close_position(position, dry_run=config.dry_run)


if __name__ == "__main__":
    run()
