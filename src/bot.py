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

from src.config import AppConfig, RiskConfig, load_config
from src.indicators import atr, rsi
from src.logger_setup import setup_logging
from src.mt5_client import MT5Client, OpenPosition
from src.notifier import EmailConfig, EmailNotifier
from src.risk_manager import RiskLimitExceeded, RiskManager
from src.strategies.breakout import BreakoutStrategy
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
# Evaluado el 23/09/2026 con el mismo backtest de 7 meses que BTC/Oro (ver
# CLAUDE.md). Queda con el codigo listo pero APAGADO (`ENABLE_ETH=false` por
# defecto) hasta que el usuario confirme sumarlo a la cuenta real.
ETHUSD_SYMBOL = "ETHUSDm"


def build_strategies(config: AppConfig) -> list[StructuralPullbackStrategy | BreakoutStrategy]:
    # Metodologia v2 (seccion 4 del sistema, 14/09/2026) para los
    # instrumentos activos. El limite dinamico de riesgo de Oro (seccion
    # 3.2: solo tomar señales cuyo SL tecnico entre en el % de riesgo
    # objetivo al lote minimo del broker) no se hardcodea aca - lo aplica
    # RiskManager en cada señal, recalculado sobre el balance real de la
    # cuenta en ese momento. Mismos parametros por defecto (RSI 35/65,
    # vela de rechazo) para los tres simbolos, ETH incluido.
    strategies: list[StructuralPullbackStrategy | BreakoutStrategy] = [
        StructuralPullbackStrategy(symbol=BTCUSD_SYMBOL, timeframe="H1"),
        StructuralPullbackStrategy(symbol=XAUUSD_SYMBOL, timeframe="H1"),
    ]
    if config.enable_eth:
        strategies.append(StructuralPullbackStrategy(symbol=ETHUSD_SYMBOL, timeframe="H1"))
    if config.enable_breakout_strategy:
        # Sistema SEPARADO de la Metodologia v2 (ruptura de consolidacion,
        # no reversion) - evaluado el 23/09/2026 y RECHAZADO (profit factor
        # 1.06-1.11, muy por debajo del 1.5 exigido, y el bucket de capital
        # que pide el usuario para esta estrategia queda bloqueado por el
        # lote minimo de BTC casi igual que Oro). Ver CLAUDE.md. Solo BTC,
        # nunca Oro/ETH (asi lo pidio el usuario).
        strategies.append(BreakoutStrategy(symbol=BTCUSD_SYMBOL, timeframe="H1"))
    return strategies


def build_notifier(config: AppConfig) -> EmailNotifier | None:
    # Notificaciones por mail (24/09/2026): APAGADAS por defecto hasta que
    # el usuario cargue sus credenciales SMTP - ver src/notifier.py y
    # CLAUDE.md ("Timeframe M30 para BTC", el problema real que resuelve).
    if not config.enable_email_notifications:
        return None
    return EmailNotifier(
        EmailConfig(
            smtp_host=config.smtp_host,
            smtp_port=config.smtp_port,
            smtp_user=config.smtp_user,
            smtp_password=config.smtp_password,
            to_email=config.notify_to_email,
        )
    )


def run() -> None:
    setup_logging()
    config = load_config()
    strategies = build_strategies(config)
    notifier = build_notifier(config)

    client = MT5Client(config.mt5)
    risk_manager = RiskManager(config.risk)

    logger.info(
        "Arrancando bot | dry_run={} | simbolos={} | timeframe=H1 | riesgo_por_operacion={}% | "
        "notificaciones_por_mail={}",
        config.dry_run,
        [s.symbol for s in strategies],
        config.risk.risk_per_trade_pct,
        config.enable_email_notifications,
    )
    if not config.dry_run:
        logger.warning("MODO REAL: el bot va a enviar ordenes reales al broker.")

    client.connect()

    # Estado de "que posicion propia del bot esta abierta en cada simbolo",
    # por simbolo (no por estrategia - dos estrategias sobre el mismo
    # simbolo, ej. BTC con Metodologia v2 + BreakoutStrategy si algun dia se
    # activa, comparten el mismo casillero de posicion). Se usa solo para
    # detectar cierres y avisar por mail - se inicializa con lo que ya este
    # abierto al arrancar, para no perderse el cierre de una posicion que
    # ya existia de una corrida anterior del bot.
    symbols = sorted({strategy.symbol for strategy in strategies})
    known_tickets: dict[str, int | None] = {}
    for symbol in symbols:
        existing = client.get_open_position_by_bot(symbol)
        known_tickets[symbol] = existing.ticket if existing else None

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
        if isinstance(strategy, BreakoutStrategy):
            logger.info(
                "{}: estrategia de ruptura con bucket de capital separado - "
                "arriesga {}% de un bucket del {}% del balance real (no del "
                "capital total). Ver CLAUDE.md.",
                strategy.symbol,
                config.breakout_risk_per_trade_pct,
                config.breakout_bucket_pct,
            )
    try:
        while True:
            for symbol in symbols:
                _check_position_closed(client, symbol, known_tickets, notifier)
            for strategy in strategies:
                try:
                    iterate(client, strategy, risk_manager, config, notifier, known_tickets)
                except RiskLimitExceeded as exc:
                    # Bloqueo esperado (posicion ya abierta, riesgo excedido,
                    # etc.) - NUNCA se notifica por mail: pasa cada 30
                    # segundos mientras haya una posicion manual abierta, y
                    # mandar un mail por cada uno seria spam puro (ver el
                    # caso real del 22-24/09/2026 en CLAUDE.md).
                    logger.warning("Operacion bloqueada por gestion de riesgo ({}): {}", strategy.symbol, exc)
                except Exception as exc:
                    logger.exception("Error inesperado en la iteracion del bot ({}).", strategy.symbol)
                    if notifier:
                        notifier.notify_error(context=strategy.symbol, message=str(exc))
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Bot detenido manualmente.")
    finally:
        client.disconnect()


def _check_position_closed(
    client: MT5Client, symbol: str, known_tickets: dict[str, int | None], notifier: EmailNotifier | None
) -> None:
    """Compara la posicion propia del bot en `symbol` contra la ultima
    conocida - si la que conociamos ya no esta, se cerro (por SL/TP del
    broker, por el bot, o manual) y se notifica. No distingue el motivo del
    cierre, solo que ya no esta - el detalle (ganancia/perdida, precio de
    cierre) sale del historial de MT5 via `get_closed_trade_info`."""
    previous_ticket = known_tickets.get(symbol)
    current = client.get_open_position_by_bot(symbol)
    current_ticket = current.ticket if current else None
    if previous_ticket is not None and current_ticket != previous_ticket:
        logger.info("{}: la posicion #{} ya no esta abierta (cerrada).", symbol, previous_ticket)
        if notifier:
            info = client.get_closed_trade_info(previous_ticket)
            notifier.notify_trade_closed(symbol=symbol, ticket=previous_ticket, info=info)
    known_tickets[symbol] = current_ticket


def iterate(
    client: MT5Client,
    strategy,
    risk_manager: RiskManager,
    config: AppConfig,
    notifier: EmailNotifier | None = None,
    known_tickets: dict[str, int | None] | None = None,
) -> None:
    account = client.get_account_info()
    # Kill switch diario: comparte el mismo contador de PnL realizado entre
    # los dos instrumentos (es un limite de cuenta, no por simbolo).
    risk_manager.check_daily_loss_limit(account.balance)

    data = client.get_rates(strategy.symbol, strategy.timeframe)

    # Limite de tiempo maximo (seccion 6.1): APAGADO por defecto
    # (`ENABLE_TIME_EXIT` no seteado o en false). El backtest del
    # 17/09/2026 mostro que empeora el profit factor 18-45% frente a no
    # tener ningun limite - se dejo el codigo listo pero inerte hasta que
    # se revalide con otras condiciones. Ver CLAUDE.md. Solo aplica a la
    # Metodologia v2 (usa RSI/ATR propios) - BreakoutStrategy no define
    # rsi_period, asi que queda afuera aunque ENABLE_TIME_EXIT este en true.
    if config.enable_time_exit and isinstance(strategy, StructuralPullbackStrategy):
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

    if isinstance(strategy, BreakoutStrategy):
        # Bucket de capital separado (pedido explicito del usuario,
        # 23/09/2026): esta estrategia NO arriesga % del capital total como
        # la Metodologia v2 - usa un bucket de `breakout_bucket_pct`% del
        # capital real, arriesgando `breakout_risk_per_trade_pct`% de ESE
        # bucket por operacion. Queda listo aunque la estrategia esta
        # RECHAZADA (ver CLAUDE.md): con el lote minimo de BTC, este bucket
        # bloquea casi todas las señales igual que le pasaba a Oro con el
        # capital total.
        sizing_balance = account.balance * (config.breakout_bucket_pct / 100.0)
        sizing_risk_manager = RiskManager(
            RiskConfig(
                risk_per_trade_pct=config.breakout_risk_per_trade_pct,
                max_daily_loss_pct=risk_manager.config.max_daily_loss_pct,
                max_open_positions=risk_manager.config.max_open_positions,
            ),
            pnl_tracker=risk_manager.pnl_tracker,
        )
    else:
        sizing_balance = account.balance
        sizing_risk_manager = risk_manager

    size_result = sizing_risk_manager.calculate_position_size(
        account_balance=sizing_balance,
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
    sizing_risk_manager.enforce_min_lot_policy(size_result, is_real_account=config.is_real_account_server)

    order = TradeOrder(
        symbol=strategy.symbol,
        signal=signal,
        volume=size_result.volume,
        stop_loss=sl_price,
        take_profit=tp_price,
    )
    client.send_order(order, dry_run=config.dry_run)

    if notifier:
        notifier.notify_trade_opened(
            symbol=strategy.symbol,
            signal=signal,
            entry_price=entry_price,
            stop_loss=sl_price,
            take_profit=tp_price,
            volume=size_result.volume,
            dry_run=config.dry_run,
        )
    if not config.dry_run and known_tickets is not None:
        # Orden real ya enviada - guardar el ticket de la posicion nueva
        # para poder detectar su cierre mas adelante (`_check_position_closed`).
        new_position = client.get_open_position_by_bot(strategy.symbol)
        if new_position is not None:
            known_tickets[strategy.symbol] = new_position.ticket


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
