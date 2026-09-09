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
  config.py                    # Carga de variables de entorno + traba de seguridad para real
  types.py                     # Signal, TradeOrder
  indicators.py                # RSI(14) y ATR(14), suavizado de Wilder
  candles.py                   # Patrones de vela: martillo, estrella fugaz, envolvente, doji
  levels.py                    # Niveles estructurales: manuales (config/levels.json) + fractales de respaldo
  risk_manager.py              # Position sizing, kill switch diario, límite de posiciones, política de lote mínimo
  strategy_base.py             # Interfaz que debe cumplir cualquier estrategia
  strategies/
    structural_pullback.py     # Estrategia real del sistema (ver sección "Estrategia" abajo)
    sma_crossover.py           # Estrategia de ejemplo, solo para referencia/tests del motor
  mt5_client.py                 # Wrapper sobre el paquete MetaTrader5
  backtester.py                  # Motor de backtesting sobre datos históricos
  bot.py                          # Loop principal en vivo (demo o real)
config/
  levels.json                     # Niveles estructurales cargados a mano, por símbolo
tests/
  test_indicators.py, test_candles.py, test_levels.py,
  test_risk_manager.py, test_backtester.py, test_structural_pullback.py
```

## Estrategia implementada

`src/strategies/structural_pullback.py` traduce la sección 10 (el
pseudocódigo "resumen ejecutable para el bot") del sistema documentado:
ruptura/rebote reciente desde un nivel → esperar el pullback → exigir vela
de rechazo (martillo/estrella fugaz) + vela de confirmación que cierre más
allá del extremo de la vela de rechazo → exigir cruce de RSI(14) sobre/bajo
50 → SL por ATR o extremo real del pullback → TP en el siguiente nivel
estructural (o un múltiplo de riesgo si ese nivel da mala relación
riesgo/beneficio).

**Decisiones tomadas para esta primera versión** (se pueden revisar
después de ver los resultados del backtest):

- **Sin filtro de tendencia de 4H** todavía — el sistema opera solo con la
  lógica de 1H. Se puede sumar un filtro de EMA50 en 4H más adelante.
- **Niveles**: primero se usan los que cargues a mano en `config/levels.json`
  para cada símbolo; si un símbolo no tiene niveles cargados, el bot cae a
  una detección automática por fractales (aproximación matemática, no
  reemplaza tu lectura de gráfico).
- **Solo el sistema estructural** de la sección 10 — el sistema de
  reversión por RSI extremo en 1H (sección 2, "corto plazo") todavía no
  está implementado.
- El bot solo actúa sobre velas ya cerradas, así que **siempre envía
  órdenes de mercado**, nunca pendientes (la variante con Buy/Sell Limit
  sobre el pullback en formación, sección 6, queda para una v2 si hace
  falta más precisión de entrada).
- El caso de "lote mínimo fuerza más riesgo del objetivo" (sección 4,
  típico en Oro con capital chico) se maneja en `RiskManager`: bloquea la
  operación en cuenta real, la deja pasar con warning en cuenta demo.

Estas son simplificaciones de un proceso que hasta ahora era discrecional
— no una traducción literal perfecta. Antes de demo, revisá con backtest
si el comportamiento en casos reales (rupturas, rebotes, distintos
instrumentos) coincide con tu criterio, y ajustá los parámetros
(`lookback_candles`, `level_proximity_atr_mult`, `sl_atr_margin_mult`,
`min_risk_reward`) que la estrategia expone en su constructor.

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
from src.strategies.structural_pullback import StructuralPullbackStrategy
# ... cargar `data` (DataFrame con columnas time, open, high, low, close)
# Antes de correrlo: cargar los niveles del simbolo en config/levels.json
strategy = StructuralPullbackStrategy(symbol="XAUUSD", timeframe="H1")
result = run_backtest(strategy, data)
print(result.summary())
```

## Correr el bot en vivo (demo o real)

```bash
python -m src.bot
```

## Próximo paso

1. Cargar los niveles estructurales reales en `config/levels.json` para
   XAU/USD, BTC/USD y US500 (los que ya venís leyendo en TradingView).
2. Correr el backtest sobre el historial real de cada instrumento y
   revisar `result.summary()` (win rate, profit factor, drawdown) contra
   el criterio de la sección 9 del sistema.
3. Ajustar los parámetros de `StructuralPullbackStrategy` según lo que
   muestre el backtest — no hay que esperar que la v1 sea perfecta.
4. Recién ahí, correr el bot contra la cuenta **demo** (`DRY_RUN=true` al
   principio, después `false` sobre demo) y repetir el control de calidad
   de la sección 9 hasta la racha de 5-8 operaciones sin error de proceso.
5. El sistema de reversión por RSI extremo en 1H (corto plazo) y el
   filtro de tendencia de 4H quedan como siguientes iteraciones.
