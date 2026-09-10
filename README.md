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
- **`BTCUSD` es el símbolo por defecto del bot** (`src/bot.py`), no
  `XAUUSD`. Con backtest real (10/09/2026, niveles automáticos por
  fractales + `RiskManager` real sobre $400) se confirmó que el lote
  mínimo de XAUUSD (0.01) fuerza ~4-7% de riesgo real por operación en
  vez del 1-1.5% objetivo, dado el ATR típico de Oro en H1 — hace falta
  del orden de $1.500+ de capital para que el lote mínimo respete el
  riesgo objetivo en ese instrumento. BTC/USD sí calza bien con $400. El
  bot loguea un warning al arrancar si se corre igual con XAUUSD por
  debajo de `XAUUSD_MIN_RECOMMENDED_BALANCE`.

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
strategy = StructuralPullbackStrategy(symbol="BTCUSD", timeframe="H1")
result = run_backtest(strategy, data)
print(result.summary())
```

También está `scripts/backtest_from_csv.py`, que corre esto mismo sobre
un CSV histórico y compara lote fijo vs. riesgo real:

```bash
python -m scripts.backtest_from_csv data/xauusd_h1.csv XAUUSD \
    --sep=";" --pip-size=0.01 --pip-value-per-lot=1.0 \
    --account-balance=400 --risk-per-trade-pct=1.5
```

## Puesta en marcha en demo (10/09/2026)

El bot **no corre en este repositorio remoto** — necesita el terminal
MetaTrader 5 real, así que se ejecuta en tu PC (o una VPS Windows) con
Exness abierto y logueado en tu cuenta demo. Pasos:

1. En esa máquina: `git clone` este repo (o `git pull` si ya lo tenés),
   y confirmá que estás parado en la rama `claude/exness-trading-bot-k8ya9k`
   (o la que tu equipo haya mergeado a `main`).
2. `python -m venv .venv && .venv\Scripts\activate` (Windows) y
   `pip install -r requirements.txt`.
3. `copy .env.example .env` y completá `MT5_LOGIN`, `MT5_PASSWORD` y
   `MT5_SERVER` con los datos de tu cuenta **demo** (el servidor lo ves
   en la ventana de login de MT5 - va a decir "Trial" o "Demo").
   Dejá `DRY_RUN=true` para el primer día.
4. `python -m src.bot` — con `DRY_RUN=true` el bot corre en vivo contra
   los precios reales de tu demo, calcula todo, pero **nunca manda
   órdenes** — solo loguea qué haría. Mirá `logs/bot.log` un día o dos
   para confirmar que arranca sin errores y que las señales que muestra
   tienen sentido.
5. Cuando estés cómodo, poné `DRY_RUN=false` en el `.env` (seguís en
   demo, no hace falta tocar `LIVE_TRADING_CONFIRMATION` - esa traba es
   solo para cuenta real) y corré `python -m src.bot` de nuevo. Ahora sí
   manda órdenes a tu cuenta demo.
6. El símbolo por defecto es **`BTCUSDm`** (ver `src/bot.py`) — el sufijo
   `"m"` depende del tipo de cuenta (Standard, en este caso; verificado
   en el Market Watch de MT5 el 10/09/2026). Si en algún momento cambiás
   de cuenta/tipo, fijate en Market Watch cómo se llaman ahí `XAUUSD` y
   `BTCUSD` exactamente, y actualizá `XAUUSD_SYMBOL`/`BTCUSD_SYMBOL` en
   `src/bot.py` y las claves de `config/levels.json` para que coincidan
   — si no, el bot no va a encontrar el símbolo y va a tirar error.
   Frecuencia esperada según el backtest: del orden de 1 señal cada
   pocos días, no varias por día - no es un bug si pasan varios días
   sin operar.
7. Actualizá `config/levels.json` cada vez que cambien tus niveles
   relevantes en TradingView - el bot los relee en cada iteración, no
   hace falta reiniciarlo.

Registrá cada operación igual que en la sección 9 de tu sistema (fecha,
motivo, resultado, lección) - el bot no lo hace todavía por vos.

## Próximo paso

1. Completar la racha de 5-8 operaciones en demo sin error de proceso
   (la definición es tuya, sección 9 del sistema) y comparar el
   profit factor real contra el del backtest (2.04 XAUUSD / 1.39 BTCUSD
   sobre 7 meses, con la configuración vigente).
2. Si el profit factor real se sostiene, evaluar el pase a cuenta real
   en BTC/USD. XAUUSD queda pausado hasta ~$1500 de capital.
3. El sistema de reversión por RSI extremo en 1H (corto plazo) y el
   filtro de tendencia de 4H quedan como siguientes iteraciones, después
   de tener resultados reales de demo con el sistema actual.
