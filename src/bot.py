"""Loop principal del bot en vivo (demo o real, segun configuracion).

Flujo por iteracion:
  1. Traer velas recientes de MT5.
  2. Pedirle una senal a la estrategia.
  3. Si hay senal de entrada, validarla contra el RiskManager
     (kill switch diario, limite de posiciones simultaneas, sizing).
  4. Enviar la orden (o simularla, si DRY_RUN=true).

Uso:
    python -m src.bot
"""
from __future__ import annotations

import time

from loguru import logger

from src.config import AppConfig, load_config
from src.logger_setup import setup_logging
from src.mt5_client import MT5Client
from src.risk_manager import RiskLimitExceeded, RiskManager
from src.strategies.structural_pullback import StructuralPullbackStrategy
from src.types import Signal, TradeOrder

POLL_INTERVAL_SECONDS = 30


def build_strategy() -> StructuralPullbackStrategy:
    # Sistema estructural con pullback (seccion 10 del documento de
    # especificacion), sin el filtro de tendencia de 4H y sin el sistema
    # de reversion por RSI extremo en 1H (quedan para una siguiente etapa).
    return StructuralPullbackStrategy(symbol="XAUUSD", timeframe="H1")


def run() -> None:
    setup_logging()
    config = load_config()
    strategy = build_strategy()

    client = MT5Client(config.mt5)
    risk_manager = RiskManager(config.risk)

    logger.info(
        "Arrancando bot | dry_run={} | simbolo={} | timeframe={}",
        config.dry_run,
        strategy.symbol,
        strategy.timeframe,
    )
    if not config.dry_run:
        logger.warning("MODO REAL: el bot va a enviar ordenes reales al broker.")

    client.connect()
    try:
        while True:
            try:
                iterate(client, strategy, risk_manager, config)
            except RiskLimitExceeded as exc:
                logger.warning("Operacion bloqueada por gestion de riesgo: {}", exc)
            except Exception:
                logger.exception("Error inesperado en la iteracion del bot.")
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Bot detenido manualmente.")
    finally:
        client.disconnect()


def iterate(client: MT5Client, strategy, risk_manager: RiskManager, config: AppConfig) -> None:
    account = client.get_account_info()
    risk_manager.check_daily_loss_limit(account.balance)
    risk_manager.check_open_positions_limit(account.open_positions)

    data = client.get_rates(strategy.symbol, strategy.timeframe)
    signal = strategy.generate_signal(data)
    if signal not in (Signal.BUY, Signal.SELL):
        return

    # La vela de confirmacion del setup ya cerro (el bot solo mira velas
    # cerradas) -> la orden siempre es de mercado, nunca pendiente
    # (ver limitacion documentada en structural_pullback.py).
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
    # por separado. Bloquea en cuenta real si el lote minimo fuerza mas
    # riesgo del configurado (seccion 4 del sistema); en demo solo loguea.
    risk_manager.enforce_min_lot_policy(size_result, is_real_account=config.is_real_account_server)

    order = TradeOrder(
        symbol=strategy.symbol,
        signal=signal,
        volume=size_result.volume,
        stop_loss=sl_price,
        take_profit=tp_price,
    )
    client.send_order(order, dry_run=config.dry_run)


if __name__ == "__main__":
    run()
