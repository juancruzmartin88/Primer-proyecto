# Primer-proyecto

Bot de trading algorítmico para Exness (MetaTrader 5), con foco en gestión
de riesgo antes que en la estrategia en sí.

## ⚠️ Advertencia

Este bot puede enviar órdenes reales a una cuenta de Exness con dinero real.
**No lo conectes a una cuenta real sin antes:**

1. Correr y revisar el backtest sobre datos históricos representativos.
2. Operarlo en **cuenta demo** durante varias semanas, en distintas
   condiciones de mercado.
3. Revisar que los límites de riesgo (`RISK_PER_TRADE_PCT`,
   `MAX_DAILY_LOSS_PCT`, `MAX_OPEN_POSITIONS`) sean los que realmente
   querés asumir.

El bot arranca siempre en modo `DRY_RUN=true` (simula órdenes, no las
envía). Pasar a envío real requiere setear explícitamente `DRY_RUN=false`
y, si el servidor de la cuenta no es una demo, además
`LIVE_TRADING_CONFIRMATION=ENTIENDO_EL_RIESGO` — es una traba deliberada
para que nadie termine operando en real por accidente.

## Arquitectura

```
src/
  config.py          # Carga de variables de entorno + traba de seguridad para real
  types.py            # Signal, TradeOrder
  risk_manager.py     # Position sizing, kill switch diario, límite de posiciones
  strategy_base.py    # Interfaz que debe cumplir cualquier estrategia
  strategies/
    sma_crossover.py  # Estrategia de EJEMPLO (placeholder) - reemplazar
  mt5_client.py        # Wrapper sobre el paquete MetaTrader5
  backtester.py         # Motor de backtesting sobre datos históricos
  bot.py                 # Loop principal en vivo (demo o real)
tests/
  test_risk_manager.py
  test_backtester.py
```

## Requisitos

- Python 3.11+
- Para operar en vivo (demo o real): terminal **MetaTrader 5 de Exness**
  instalado en la misma máquina (Windows, o Windows en una VPS). El
  paquete `MetaTrader5` de Python solo funciona contra un terminal real.
- Backtesting y tests **no** requieren MT5 instalado, corren en cualquier
  plataforma.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Editar .env con las credenciales de la cuenta (demo primero)
```

## Correr los tests

```bash
pytest tests/ -v
```

## Correr un backtest

```python
from src.backtester import run_backtest
from src.strategies.sma_crossover import SmaCrossoverStrategy
# ... cargar `data` (DataFrame con columnas time, open, high, low, close)
strategy = SmaCrossoverStrategy(symbol="EURUSD", timeframe="M15")
result = run_backtest(strategy, data)
print(result.summary())
```

## Correr el bot en vivo (demo o real)

```bash
python -m src.bot
```

## Próximo paso

La estrategia incluida (`SmaCrossoverStrategy`) es solo un placeholder
para validar que el esqueleto funciona de punta a punta. El siguiente
paso es reemplazarla por la estrategia real, implementando la interfaz
`Strategy` en `src/strategy_base.py` con las reglas de entrada/salida
concretas.
