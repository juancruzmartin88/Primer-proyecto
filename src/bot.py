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

from src.config import load_config
from src.logger_setup import setup_logging
from src.mt5_client import MT5Client
from src.risk_manager import RiskLimitExceeded, RiskManager
from src.strategies.sma_crossover import SmaCrossoverStrategy
from src.types import Signal, TradeOrder

POLL_INTERVAL_SECONDS = 30


def build_strategy() -> SmaCrossoverStrategy:
    # PLACEHOLDER: reemplazar por la estrategia real una vez definida.
    return SmaCrossoverStrategy(symbol="EURUSD", timeframe="M15")


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
                iterate(client, strategy, risk_manager, config.dry_run)
            except RiskLimitExceeded as exc:
                logger.warning("Operacion bloqueada por gestion de riesgo: {}", exc)
            except Exception:
                logger.exception("Error inesperado en la iteracion del bot.")
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Bot detenido manualmente.")
    finally:
        client.disconnect()


def iterate(client: MT5Client, strategy, risk_manager: RiskManager, dry_run: bool) -> None:
    account = client.get_account_info()
    risk_manager.check_daily_loss_limit(account.balance)
    risk_manager.check_open_positions_limit(account.open_positions)

    data = client.get_rates(strategy.symbol, strategy.timeframe)
    signal = strategy.generate_signal(data)
    if signal not in (Signal.BUY, Signal.SELL):
        return

    entry_price = data["close"].iloc[-1]
    sl_price = strategy.stop_loss_price(data, signal)
    tp_price = strategy.take_profit_price(data, signal)
    pip_size, pip_value_per_lot = client.get_symbol_pip_info(strategy.symbol)

    volume = risk_manager.calculate_position_size(
        account_balance=account.balance,
        entry_price=entry_price,
        stop_loss_price=sl_price,
        pip_value_per_lot=pip_value_per_lot,
        pip_size=pip_size,
    )

    order = TradeOrder(
        symbol=strategy.symbol,
        signal=signal,
        volume=volume,
        stop_loss=sl_price,
        take_profit=tp_price,
    )
    client.send_order(order, dry_run=dry_run)


if __name__ == "__main__":
    run()
