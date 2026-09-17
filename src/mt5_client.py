"""Wrapper fino sobre el paquete `MetaTrader5`.

Centraliza toda la interaccion con el terminal (login, datos historicos,
envio de ordenes) para que el resto del bot no dependa directamente de la
API de MetaTrader5 y sea mas facil de testear con mocks.

Nota: el paquete `MetaTrader5` solo funciona sobre un terminal MT5 real
(Windows, o Wine en Linux) - por eso se importa de forma perezosa, para
que el resto del proyecto (backtesting, tests, gestion de riesgo) se
pueda usar sin tener el terminal instalado.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
from loguru import logger

from src.config import MT5Config
from src.types import Signal, TradeOrder

# Magic number propio del bot: identifica sus ordenes/posiciones frente a
# cualquier operacion manual del usuario en la misma cuenta. Se usa tanto
# para enviar ordenes (`send_order`) como para decidir que posiciones puede
# tocar el bot despues (`get_open_position_by_bot`, `close_position`) - una
# posicion manual del usuario nunca tiene este magic, asi que el bot jamas
# la cierra por su cuenta (seccion 6 del sistema: el cierre manual queda a
# criterio del usuario, sin objecion del bot).
BOT_MAGIC = 123456


class MT5ConnectionError(Exception):
    pass


class OrderRejected(Exception):
    """Rechazo local (antes de tocar el broker) por no cumplir una traba de seguridad."""


@dataclass(frozen=True)
class AccountInfo:
    balance: float
    equity: float
    currency: str
    leverage: int
    open_positions: int


@dataclass(frozen=True)
class SymbolTradeSpecs:
    pip_size: float
    pip_value_per_lot: float
    min_lot: float
    lot_step: float


@dataclass(frozen=True)
class OpenPosition:
    """Posicion abierta por el bot mismo (ver `BOT_MAGIC`)."""

    ticket: int
    symbol: str
    signal: Signal
    volume: float
    price_open: float
    time_open: datetime
    stop_loss: float
    take_profit: float


class MT5Client:
    def __init__(self, config: MT5Config) -> None:
        self.config = config
        self._mt5 = None

    def _mt5_module(self):
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except ImportError as exc:
                raise MT5ConnectionError(
                    "No se pudo importar el paquete MetaTrader5. Este paquete requiere "
                    "un terminal MetaTrader 5 instalado (Windows nativo, o Wine en Linux). "
                    "Instala las dependencias en la maquina/VPS donde va a correr el bot."
                ) from exc
            self._mt5 = mt5
        return self._mt5

    def connect(self) -> None:
        mt5 = self._mt5_module()
        kwargs = {}
        if self.config.path:
            kwargs["path"] = self.config.path
        initialized = mt5.initialize(
            login=self.config.login,
            password=self.config.password,
            server=self.config.server,
            **kwargs,
        )
        if not initialized:
            error = mt5.last_error()
            raise MT5ConnectionError(f"Fallo la conexion a MT5: {error}")
        logger.info("Conectado a MT5: servidor={} login={}", self.config.server, self.config.login)

    def disconnect(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()
            logger.info("Desconectado de MT5.")

    def get_account_info(self) -> AccountInfo:
        mt5 = self._mt5_module()
        info = mt5.account_info()
        if info is None:
            raise MT5ConnectionError("No se pudo obtener account_info(); revisar conexion.")
        positions = mt5.positions_get()
        return AccountInfo(
            balance=info.balance,
            equity=info.equity,
            currency=info.currency,
            leverage=info.leverage,
            open_positions=len(positions) if positions is not None else 0,
        )

    def get_rates(self, symbol: str, timeframe: str, count: int = 200) -> pd.DataFrame:
        mt5 = self._mt5_module()
        tf_constant = getattr(mt5, f"TIMEFRAME_{timeframe}", None)
        if tf_constant is None:
            raise ValueError(f"Timeframe invalido: {timeframe}")
        rates = mt5.copy_rates_from_pos(symbol, tf_constant, 0, count)
        if rates is None:
            raise MT5ConnectionError(f"No se pudieron obtener velas para {symbol}/{timeframe}")
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    def get_open_positions_count(self, symbol: str) -> int:
        """Posiciones abiertas para UN simbolo puntual (no el total de la cuenta).

        Con dos instrumentos operando en simultaneo (BTC + Oro, 14/09/2026),
        el limite de posiciones abiertas (`MAX_OPEN_POSITIONS`) se aplica por
        instrumento, no sobre el total de la cuenta - por eso esto va
        separado de `get_account_info().open_positions` (que sigue siendo
        el total, para referencia/logging).
        """
        mt5 = self._mt5_module()
        positions = mt5.positions_get(symbol=symbol)
        return len(positions) if positions is not None else 0

    def get_open_position_by_bot(self, symbol: str) -> OpenPosition | None:
        """La posicion abierta que el bot mismo abrio para este simbolo (por
        `BOT_MAGIC`), o None si no hay. Si el usuario tiene una posicion
        manual en el mismo simbolo, esto la ignora a proposito - el bot
        nunca gestiona (ni cierra por tiempo) una operacion que no abrio el.
        """
        mt5 = self._mt5_module()
        positions = mt5.positions_get(symbol=symbol)
        if not positions:
            return None
        for p in positions:
            if p.magic != BOT_MAGIC:
                continue
            direction = Signal.BUY if p.type == mt5.POSITION_TYPE_BUY else Signal.SELL
            return OpenPosition(
                ticket=p.ticket,
                symbol=p.symbol,
                signal=direction,
                volume=p.volume,
                price_open=p.price_open,
                time_open=datetime.fromtimestamp(p.time, tz=timezone.utc),
                stop_loss=p.sl,
                take_profit=p.tp,
            )
        return None

    def close_position(self, position: OpenPosition, *, dry_run: bool) -> dict:
        """Cierra una posicion abierta por el bot (limite de tiempo, seccion
        6.1 del sistema) con una orden de mercado en sentido contrario."""
        if dry_run:
            logger.info("[DRY_RUN] Se simularia el cierre de la posicion {} ({})", position.ticket, position.symbol)
            return {"dry_run": True, "position": position}

        mt5 = self._mt5_module()
        opposite_type = mt5.ORDER_TYPE_SELL if position.signal == Signal.BUY else mt5.ORDER_TYPE_BUY
        symbol_info_tick = mt5.symbol_info_tick(position.symbol)
        if symbol_info_tick is None:
            raise MT5ConnectionError(f"No se pudo obtener el precio actual de {position.symbol}")
        price = symbol_info_tick.bid if position.signal == Signal.BUY else symbol_info_tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": opposite_type,
            "position": position.ticket,
            "price": price,
            "deviation": 10,
            "magic": BOT_MAGIC,
            "comment": "cierre por limite de tiempo (seccion 6.1)",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("Cierre de posicion rechazado por el broker: {} (request={})", result, request)
            raise MT5ConnectionError(f"order_send (cierre) fallo con retcode={result.retcode}: {result.comment}")
        logger.info("Posicion cerrada por limite de tiempo: {}", result)
        return {"dry_run": False, "result": result}

    def get_symbol_trade_specs(self, symbol: str) -> SymbolTradeSpecs:
        """Especificaciones del simbolo necesarias para dimensionar posiciones."""
        mt5 = self._mt5_module()
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            raise MT5ConnectionError(f"No se encontro informacion del simbolo {symbol}")
        pip_size = symbol_info.point * 10 if symbol_info.digits in (3, 5) else symbol_info.point
        pip_value_per_lot = symbol_info.trade_tick_value * (pip_size / symbol_info.trade_tick_size)
        return SymbolTradeSpecs(
            pip_size=pip_size,
            pip_value_per_lot=pip_value_per_lot,
            min_lot=symbol_info.volume_min,
            lot_step=symbol_info.volume_step,
        )

    def send_order(self, order: TradeOrder, *, dry_run: bool) -> dict:
        # Traba dura: nunca se manda una orden sin SL/TP activos (seccion 4
        # del sistema: "verificar siempre que los toggles de SL/TP esten
        # activos antes de confirmar una orden").
        if not order.stop_loss or not order.take_profit:
            raise OrderRejected(
                "Orden rechazada: falta stop_loss o take_profit. Nunca se envia "
                "una orden sin proteccion activa."
            )

        if dry_run:
            logger.info("[DRY_RUN] Se simularia orden: {}", order)
            return {"dry_run": True, "order": order}

        mt5 = self._mt5_module()
        order_type = mt5.ORDER_TYPE_BUY if order.signal == Signal.BUY else mt5.ORDER_TYPE_SELL
        symbol_info_tick = mt5.symbol_info_tick(order.symbol)
        if symbol_info_tick is None:
            raise MT5ConnectionError(f"No se pudo obtener el precio actual de {order.symbol}")
        price = symbol_info_tick.ask if order.signal == Signal.BUY else symbol_info_tick.bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": order.symbol,
            "volume": order.volume,
            "type": order_type,
            "price": price,
            "sl": order.stop_loss,
            "tp": order.take_profit,
            "deviation": 10,
            "magic": BOT_MAGIC,
            "comment": order.comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("Orden rechazada por el broker: {} (request={})", result, request)
            raise MT5ConnectionError(f"order_send fallo con retcode={result.retcode}: {result.comment}")
        logger.info("Orden ejecutada: {}", result)
        return {"dry_run": False, "result": result}
