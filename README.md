# Primer-proyecto

Bot de trading algorítmico para Exness (MetaTrader 5), con foco en gestión
de riesgo antes que en la estrategia en sí.

## ⚠️ Advertencia

**Este bot opera con dinero real desde el 14/09/2026** (cuenta real del
usuario, ver `CLAUDE.md` para el estado vigente). Si estás arrancando de
cero con este repo en otra cuenta, no lo conectes a una cuenta real sin
antes:

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
  risk_manager.py              # Position sizing, kill switch diario, límite de posiciones (por instrumento), política de lote mínimo
  strategy_base.py             # Interfaz que debe cumplir cualquier estrategia
  strategies/
    structural_pullback.py     # Estrategia real del sistema (Metodología v2 — ver sección "Estrategia" abajo)
    sma_crossover.py           # Estrategia de ejemplo, solo para referencia/tests del motor
  mt5_client.py                 # Wrapper sobre el paquete MetaTrader5
  time_exit.py                    # Limite de tiempo maximo para posiciones abiertas (implementado, APAGADO — ver mas abajo)
  backtester.py                  # Motor de backtesting sobre datos históricos
  bot.py                          # Loop principal en vivo (demo o real) — BTC + Oro en simultáneo
config/
  levels.json                     # Niveles estructurales cargados a mano, por símbolo
tests/
  test_indicators.py, test_candles.py, test_levels.py, test_time_exit.py,
  test_risk_manager.py, test_backtester.py, test_structural_pullback.py
```

## Estrategia implementada — Metodología v2 (14/09/2026)

`src/strategies/structural_pullback.py` traduce la sección 4 del sistema
de trading vigente (reemplaza al enfoque anterior de "entrar en la vela de
ruptura"). Una señal requiere que se cumplan, todos a la vez, sobre las
últimas dos velas cerradas de un símbolo:

1. **Nivel técnico relevante tocado** — desde el 22/09/2026, los niveles
   cargados a mano en `config/levels.json` **se combinan siempre** con
   fractales automáticos (`src/levels.py`), no es uno u otro. Antes, si
   había niveles manuales cargados, los fractales nunca se usaban — eso
   causó un incidente real: los niveles de BTC quedaron desactualizados
   (~$77-79k cargados el 09/09) mientras el precio subía a ~$86k, y el bot
   dejó de poder operar BTC sin ningún aviso porque el respaldo automático
   nunca se activaba. Ahora el bot no depende de que alguien mantenga el
   archivo al día — los manuales son un complemento al análisis del
   usuario, no un requisito para operar.
2. **Extremo de RSI(14) real** — el RSI tuvo que cruzar por debajo de 30
   (sobreventa) o por encima de 70 (sobrecompra) en algún momento reciente
   (ventana configurable, `extreme_lookback`), no solo cruzar el nivel 50.
3. **Giro confirmado del RSI** — no alcanza con tocar el extremo: para la
   vela de confirmación el RSI ya tiene que haber cruzado de vuelta el
   umbral (30/70). No se exige que el cruce ocurra en la vela de rechazo
   misma — en los casos reales la recuperación es progresiva a lo largo de
   varias velas.
4. **Vela de rechazo (martillo/estrella fugaz) + vela de confirmación** que
   cierre a favor de la operación — igual que antes, y ahora además con
   **volumen** de la vela de rechazo por encima del promedio reciente (si
   los datos traen columna de volumen; los CSV de backtest de Twelve Data
   usados hasta ahora no la traen, así que ese chequeo no aplica sobre esos
   backtests — en vivo MT5 sí entrega `tick_volume` en cada vela).

SL por ATR(14) o extremo real del pullback (el que sea más conservador). TP
en el siguiente nivel estructural, o un múltiplo de riesgo si ese nivel da
mala relación riesgo/beneficio — sin cambios respecto a la versión anterior.

**Decisiones de arquitectura (14/09/2026, antes de activar cuenta real):**

- **Orden de mercado en la vela de confirmación ya cerrada**, no Buy
  Stop/Sell Stop pendiente. El bot solo actúa sobre velas cerradas, así que
  en la práctica ya entra "después" de que el rebote arrancó — similar en
  espíritu a un Stop, sin la complejidad operacional de gestionar órdenes
  pendientes (colocar, vigilar, cancelar) en un sistema recién puesto en
  producción con dinero real.
- **Riesgo por operación: 2% fijo**, igual para BTC y Oro (antes 1.5%). Con
  el capital real (~$650) esto reproduce el límite de 13 puntos de SL para
  Oro de la sección 3.2 del sistema — ese límite no está hardcodeado en
  ningún lado: surge de `RiskManager.calculate_position_size` +
  `enforce_min_lot_policy`, que en cuenta real **bloquea** cualquier señal
  cuyo SL técnico, al lote mínimo del broker, fuerce más del 2% de riesgo
  real sobre el balance actual — se recalcula solo con el balance vigente
  de la cuenta, sin ningún ajuste manual si el capital cambia.
- **Dos instrumentos en simultáneo** (BTC + Oro): `MAX_OPEN_POSITIONS` es
  ahora un límite **por instrumento**, no total de la cuenta — una señal de
  Oro no se pierde porque BTC tenga una posición abierta, y viceversa. El
  kill switch diario (`MAX_DAILY_LOSS_PCT`) sí es compartido entre los dos.
- **Sin filtro de tendencia de 4H** todavía.
- **Sin sistema de reversión por RSI extremo como estrategia separada** —
  la Metodología v2 ya incorpora el chequeo de RSI extremo (30/70) dentro
  de la única lógica de entrada, así que el viejo plan de "sistema corto
  plazo aparte" queda absorbido acá, no pendiente.
- **`XAUUSDm`/`BTCUSDm` son los dos símbolos que opera el bot** (`src/bot.py`).
  El sufijo `"m"` depende del tipo de cuenta — reverificado en la cuenta
  real el 16/09/2026, coincide con la demo.
- **`ETHUSDm` está preparado en el código pero APAGADO** (`ENABLE_ETH=false`).
  Evaluado el 23/09/2026 con los mismos parámetros de BTC (RSI 35/65, vela
  de rechazo, riesgo 2%) — el backtest de 7 meses dio profit factor 1.09 y
  drawdown 23.3% (vs. PF 1.88 / DD 7.6% de BTC), no cumple el criterio que
  el usuario había fijado para activarlo (PF > 1.5). Ver CLAUDE.md para el
  detalle completo y la advertencia sobre las specs de contrato de ETH
  (pip_size/pip_value) todavía sin verificar contra el Market Watch real.
- **Sin límite de tiempo máximo por posición** (`ENABLE_TIME_EXIT=false`).
  Hay un límite de tiempo implementado (`src/time_exit.py`, sección 6.1 del
  sistema) pero el backtest del 17/09/2026 mostró que empeora el profit
  factor entre 18% y 45% frente a no tener ninguno — corta operaciones
  lentas que igual iban camino al TP. Queda listo pero apagado; ver
  `CLAUDE.md` para la tabla completa antes de activarlo.

Estas son simplificaciones de un proceso que hasta ahora era discrecional
— no una traducción literal perfecta. Ajustá los parámetros
(`lookback_candles`, `level_proximity_atr_mult`, `sl_atr_margin_mult`,
`min_risk_reward`, `extreme_lookback`, `volume_confirmation_mult`) que la
estrategia expone en su constructor si el backtest muestra que hace falta.

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
# Editar .env con las credenciales de la cuenta
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
    --account-balance=650 --risk-per-trade-pct=2.0
```

## Puesta en marcha (cuenta real, 14/09/2026)

El bot **no corre en este repositorio remoto** — necesita el terminal
MetaTrader 5 real, así que se ejecuta en tu PC (o una VPS Windows) con
Exness abierto y logueado en tu cuenta. Pasos:

1. En esa máquina: `git pull` sobre la rama
   `claude/exness-trading-bot-k8ya9k` para traer la Metodología v2.
2. `.venv\Scripts\activate` (si ya tenías el entorno armado de la demo, no
   hace falta recrearlo) y `pip install -r requirements.txt` de nuevo por
   si hay dependencias nuevas.
3. **Verificá el sufijo de símbolo en el Market Watch de la cuenta real**
   (Herramientas → Symbols, o buscá XAU/BTC directamente) — puede no ser
   `"m"` como en la demo Standard. Si es distinto, avisame para actualizar
   `XAUUSD_SYMBOL`/`BTCUSD_SYMBOL` en `src/bot.py` y las claves de
   `config/levels.json`.
4. Actualizá el `.env` con los datos de la cuenta **real**: `MT5_LOGIN`,
   `MT5_PASSWORD`, `MT5_SERVER` (el que muestra MT5 al loguearte — ya NO
   va a decir "Trial"/"Demo"), `RISK_PER_TRADE_PCT=2.0`. Dejá
   `DRY_RUN=true` para la primera puesta en marcha.
5. `python -m src.bot` con `DRY_RUN=true` — corre en vivo contra los
   precios reales de tu cuenta real, calcula todo, pero **nunca manda
   órdenes**. Confirmá en la consola que conecta bien a los dos símbolos y
   que no tira errores, al menos un rato antes de destrabar envío real.
6. Recién ahí: `DRY_RUN=false` y, como el servidor ya no es demo, agregá
   `LIVE_TRADING_CONFIRMATION=ENTIENDO_EL_RIESGO` en el `.env` (sin esto el
   bot rechaza arrancar en real — traba deliberada). Corré `python -m
   src.bot` de nuevo. Ahora sí manda órdenes reales.
7. El bot opera **BTC y Oro en simultáneo**, cada uno con su propio límite
   de posiciones abiertas. Frecuencia esperada según el backtest anterior:
   del orden de 1 señal cada pocos días por instrumento — no es un bug si
   pasan varios días sin operar ninguno de los dos.
8. Actualizá `config/levels.json` cada vez que cambien tus niveles
   relevantes en TradingView - el bot los relee en cada iteración, no
   hace falta reiniciarlo.

Registrá cada operación igual que en la sección 9 de tu sistema (fecha,
motivo, resultado, lección) - el bot no lo hace todavía por vos.

## Backtest de validación de la v2 (14/09/2026)

Sobre 7 meses de H1 (5000 velas c/u), $650 de balance, 2% de riesgo,
**bloqueando** cualquier señal cuyo SL fuerce más riesgo del objetivo al
lote mínimo (el comportamiento real del bot en cuenta real):

| Instrumento | Trades | Profit factor | Win rate | Max drawdown |
|---|---|---|---|---|
| XAUUSD | 0 | — | — | — |
| BTCUSD | 33 | 1.36 | 39.4% | 11.9% |

Con $650, ninguna de las 35 señales de Oro detectadas en 7 meses tuvo un SL
técnico lo bastante ajustado para el 2% de riesgo al lote mínimo — no es un
bug, es la regla de la sección 3.2 haciendo su trabajo. Oro va a quedar sin
operar en la práctica hasta que el capital crezca; el código no necesita
ningún cambio cuando eso pase. Ver `CLAUDE.md` para el detalle completo
(incluye la corrida exploratoria sin el bloqueo, para referencia).

Ojo: los CSV de backtest no tienen columna de volumen, así que esta corrida
no ejercita el chequeo de volumen de la v2 (sí va a estar activo en vivo,
con los datos de MT5) — la frecuencia/calidad real puede diferir un poco.

## Umbral de RSI relajado a 35/65 (20/09/2026)

`rsi_oversold`/`rsi_overbought` bajaron de 30/70 a 35/65 por defecto —
validado con backtest comparando 4 variantes del filtro de entrada (RSI
estricto/relajado × con/sin vela de rechazo). En BTC, relajar solo el RSI
(sin tocar la vela de rechazo) sube el profit factor de 1.73 a **1.88**, el
win rate de 44.4% a **47.5%**, y más que duplica el PnL total — validado
también con un split del período en dos mitades independientes. Sacar la
vela de rechazo, en cambio, empeora fuerte en cualquier combinación (el
drawdown se dispara a 23-31%) — esa parte del filtro se mantiene igual. Ver
`CLAUDE.md` para la tabla completa.

## Próximo paso

1. Juntar operaciones reales de la cuenta real con la Metodología v2 (RSI
   35/65) y compararlas contra el número vigente (PF 1.88 BTC realista).
2. El sistema de reversión por RSI extremo ya no es un ítem pendiente
   aparte — quedó absorbido dentro de la Metodología v2. El filtro de
   tendencia de 4H y las notificaciones (Telegram) siguen pendientes,
   no empezar sin que el usuario lo pida.
