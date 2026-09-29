# Contexto del proyecto (leer antes de tocar nada)

Bot de trading algorítmico para el usuario, desarrollado con Claude a lo
largo de varias sesiones (empezó 09/09/2026, demo en producción desde
10/09/2026, **cuenta real desde 14/09/2026**). Este archivo existe para que
una sesión nueva de Claude Code tenga el contexto completo sin tener que
releer todo el historial de chat.

## Estado actual (14/09/2026, pase a cuenta real)

**El bot pasa a operar con dinero real**, en la PC del usuario (Windows).
La cuenta demo (`198944861`, `Exness-MT5Trial11`, $400, solo BTCUSDm) queda
como referencia histórica — el `.env` de producción ahora apunta a la
cuenta real.

- Capital real: ~$654.77 USD (depósito completado el 15/09/2026; sufijo "m"
  reverificado en la cuenta real el 16/09/2026, coincide con la demo).
- Símbolos operados: **`BTCUSDm` y `XAUUSDm` en simultáneo** (el sufijo "m"
  hay que reverificarlo en el Market Watch de la cuenta real — puede no
  coincidir con el de la demo Standard, ver decisión 3 más abajo).
- Riesgo configurado: `RISK_PER_TRADE_PCT=2.0` (subió de 1.5),
  `MAX_DAILY_LOSS_PCT=3.0` (compartido entre los dos instrumentos),
  `MAX_OPEN_POSITIONS=1` **por instrumento** (no total de la cuenta - ver
  decisión 7).
- `DRY_RUN` recomendado en `true` para la primera puesta en marcha en la
  cuenta real (validar conexión/sizing/símbolos antes de destrabar envío
  real), aunque en demo el usuario había preferido saltar directo a
  `DRY_RUN=false` - con dinero real de por medio la recomendación cambia.

El bot corre en la PC del usuario, no en este entorno remoto — este sandbox
no tiene MetaTrader 5 ni acceso a la cuenta. Si el usuario pide "revisar qué
hizo el bot", la única fuente de verdad es lo que él mismo reporte (capturas
de MT5, del log `logs/bot.log`, o de su planilla de registro) - no asumas
que podés consultarlo directamente.

**Zona horaria del usuario: Argentina (UTC-3).** La fecha/hora de sistema de
este entorno corre en UTC, así que va a mostrar un día adelantado respecto a
lo que ve el usuario durante buena parte del día (ej.: acá ya es 12/09 a la
madrugada cuando en Argentina todavía es 11/09 a la noche). Antes de marcar
una inconsistencia de fecha en algo que reporte el usuario (planilla de
registro, capturas de MT5, etc.), convertir mentalmente a UTC-3 en vez de
asumir que está mal cargado.

## Decisiones clave y por qué (para no repreguntarlas)

1. **Estrategia: Metodología v2** (`src/strategies/structural_pullback.py`,
   reescrita 14/09/2026), traduce la sección 4 del sistema vigente del
   usuario. Reemplaza tanto el v1 (cruce de RSI por 50) como el viejo plan
   de "sistema corto plazo por RSI extremo aparte" - v2 ya combina nivel
   estructural + RSI extremo real (cruce de 35/65, no solo 50 - bajó de
   30/70 el 20/09/2026, ver decisión 11) + giro de RSI confirmado + vela de
   rechazo/confirmación + volumen (si los datos lo traen). Confirmada con
   las dos primeras operaciones reales que la aplicaron completa:
   BTC +$11.00 (11/09) y Oro +$134.07 (14/09), ambas TP.
2. **XAUUSD ya NO está pausado** (a diferencia de la decisión del
   10/09/2026 con $400 de capital). En su lugar, la sección 3.2 del sistema
   define una regla dinámica: con el capital real y 2% de riesgo objetivo,
   el bot descarta automáticamente cualquier señal de Oro cuyo SL técnico,
   al lote mínimo del broker, fuerce más riesgo del objetivo - lo hace
   `RiskManager.enforce_min_lot_policy` bloqueando en cuenta real, sin
   ningún número hardcodeado (se recalcula solo si cambia el balance). Con
   ~$650 esto equivale aproximadamente a exigir un SL técnico de ~13 puntos
   o menos en Oro.
3. **Sufijo "m" en los símbolos**: verificado para la cuenta demo Standard
   (`Exness-MT5Trial11`) el 10/09/2026, y **reverificado en la cuenta real
   Standard (`Exness-MT5Real11`) el 16/09/2026** - coincide, sigue siendo
   "m". `src/bot.py` tiene las constantes `XAUUSD_SYMBOL`/`BTCUSD_SYMBOL`
   para esto, sin cambios.
4. **Umbrales de la estrategia relajados el 10/09/2026** (siguen vigentes
   en v2, no se tocaron de nuevo): sin requisito de que la confirmación
   cierre más allá del extremo de la vela de rechazo, y
   `rejection_wick_ratio` en 1.5x en vez de 2.0x.
5. **Niveles estructurales** (`config/levels.json`): cargados a mano por el
   usuario, con fallback automático a fractales. Ya tiene cargadas las
   claves `XAUUSDm` y `BTCUSDm` (falta reverificar si el sufijo cambia en
   la cuenta real).
6. **Gestión de riesgo real ya validada contra el historial real del
   usuario** (16 operaciones manuales, 30/08-09/09/2026): el `RiskManager`
   elimina por diseño los dos peores incidentes de ese historial (un error
   de cálculo manual que expuso 106% del capital en una operación, y una
   orden enviada sin SL/TP activo).
7. **Decisiones de arquitectura del 14/09/2026** (elegidas explícitamente
   por el usuario entre varias opciones, no asumidas):
   - Riesgo por operación: **2% fijo para ambos instrumentos** (no
     diferenciado por "mediano/largo" vs "corto plazo" como sugería el
     documento - la Metodología v2 unificó la lógica de entrada en una
     sola, así que se unificó también el riesgo).
   - Tipo de orden: **mercado en la vela de confirmación ya cerrada**, no
     Buy Stop/Sell Stop pendiente (evita construir gestión de órdenes
     pendientes - colocar/vigilar/cancelar - en el primer despliegue real).
   - Posiciones simultáneas: **1 por instrumento** (2 en total posible
     entre BTC y Oro), no 1 total de la cuenta.
8. **Saltó el criterio propio del usuario para pasar a cuenta real**
   (documentado en la versión anterior de este archivo: sostener el profit
   factor real + racha de 5-8 operaciones sin error de proceso antes de
   pasar a real). Solo hubo 1 operación real en demo antes del pase
   (BTC +$11, 11/09). Decisión consciente del usuario, marcada explícitamente
   como tal en la conversación - no se lo bloqueó, pero quedó anotado.
9. **No hay chequeo automático de calendario económico** (NFP, IPC, Fed).
   No hay ninguna fuente de datos conectada a esta sesión con calendario
   macro - la sección 4.1 del sistema ("tras un shock macro, esperar
   confirmación extra") queda como criterio manual del usuario, no
   implementado en código.
10. **Límite de tiempo máximo (sección 6.1) — implementado, pero APAGADO
    (17/09/2026)**: motivado por una operación de BTC post-Fed (16/09) que
    quedó abierta ~24hs lateralizando sin acercarse a TP/SL, cerrada manual
    en apenas +$0.47. Se implementó `src/time_exit.py` (lógica pura,
    testeada) + integración en `bot.py`/`mt5_client.py`, pero el backtest
    sobre 7 meses de BTC (ver sección de abajo) mostró que **cualquier
    umbral probado (4/8/12/24hs) empeora el profit factor entre 18% y
    45%** frente a no tener ningún límite - corta operaciones lentas que
    igual iban camino al TP (la asimetría ganancia grande/pérdida chica es
    el motor del sistema). Decisión: se deja el código listo pero inerte
    (`ENABLE_TIME_EXIT=false` en `.env`, default también en `config.py`) -
    no activar sin volver a correr el backtest y mostrar una mejora real.
    El caso puntual del 16/09 se interpretó como ruido normal del sistema,
    no como una falla estructural a corregir.
11. **Umbral de RSI extremo relajado de 30/70 a 35/65 (20/09/2026) —
    ACEPTADO**, a diferencia del límite de tiempo. El usuario preguntó si
    el doble filtro (RSI extremo real + vela de rechazo) era demasiado
    estricto. Se probaron 4 variantes sobre BTC/Oro (ver backtest más
    abajo): relajar solo el RSI (manteniendo la vela de rechazo) mejora
    profit factor, win rate y PnL a la vez en BTC, validado también con un
    split del período en dos mitades independientes. Sacar la vela de
    rechazo, en cambio, empeora fuerte en cualquier combinación - esa parte
    del filtro se mantiene intacta. `rsi_oversold`/`rsi_overbought` ahora
    son 35.0/65.0 por defecto en `StructuralPullbackStrategy` (antes
    30.0/70.0).
12. **INCIDENTE (22/09/2026): los niveles manuales de BTC quedaron
    obsoletos y el bot dejó de poder operar sin que nada lo avisara —
    corregido de raíz, no con un parche.** Los niveles de `BTCUSDm` se
    habían cargado el 09/09/2026 (~77.000-79.400); para el 22/09 el precio
    ya operaba a ~86.000 (>5.000 puntos de distancia). Como
    `get_levels_for_symbol` usaba SOLO los niveles manuales cuando la
    lista no estaba vacía (cayendo a fractales automáticos solo si estaba
    vacía), el respaldo por fractales **nunca se activó** para BTC — la
    condición de "nivel técnico tocado" (punto 1 de 4 de la Metodología
    v2) no se pudo cumplir nunca, así que el bot no operó BTC durante ese
    tramo, sin ningún error ni log que lo destacara. El usuario lo detectó
    él mismo notando que "hubo condiciones para operar y el bot no lo
    hizo". Preguntó, con razón, por qué iba a tener que estar pendiente de
    avisar manualmente cada vez que esto pasara, potencialmente de
    madrugada.
    **Arreglo**: `get_levels_for_symbol` (`src/levels.py`) ahora combina
    SIEMPRE manuales + fractales (unión, no preferencia) - el filtro de
    proximidad de la estrategia ya descarta los niveles lejanos, así que
    combinar no ensucia nada. El bot ya no depende de que el usuario
    actualice el archivo para seguir operando; los niveles manuales pasan
    a ser un complemento (capturan zonas que el usuario ve en su análisis
    y que un fractal reciente no necesariamente detecta), no un requisito.
    Revalidado con el mismo backtest de siempre sobre los datos históricos
    (que nunca tocaban los niveles manuales por un mismatch de nombre de
    símbolo - ver más abajo) - los números no cambiaron nada, confirma que
    no hay regresión. `config/levels.json` también se actualizó con los
    niveles reales vigentes del usuario (BTCUSDm: `[82046.15]`; XAUUSDm
    sumó `4395.0`).
13. **ETH evaluado como tercer símbolo (23/09/2026) — código listo pero NO
    activado.** Con exactamente los mismos parámetros de BTC (RSI 35/65,
    vela de rechazo, riesgo 2%), el backtest de 7 meses dio PF 1.09 y
    drawdown 23.3% (vs. PF 1.88 / DD 7.6% de BTC) - no cumple el criterio
    que el propio usuario fijó para activarlo (PF > 1.5). Queda detrás de
    `ENABLE_ETH=false` (default), con `ETHUSD_SYMBOL` ya definido en
    `src/bot.py` - ver la sección de backtest más abajo para el detalle y
    la advertencia sobre las specs de contrato de ETH sin verificar.
14. **Estrategia de ruptura de consolidación evaluada (23/09/2026) — código
    listo pero RECHAZADA.** Sistema separado de la Metodología v2 (ruptura
    de rango, no reversión), solo sobre BTC. Falla las dos condiciones que
    el usuario pidió confirmar: profit factor 1.06-1.11 (vs. 1.5 exigido,
    ni el trailing stop desde 1R lo mejora - de hecho lo empeora a 0.79) y
    el bucket de capital pedido (15% del balance, riesgo 3% del bucket)
    queda bloqueado por el lote mínimo de BTC casi igual que a Oro con el
    capital total (2 de 47 señales pasan, ambas perdedoras). Queda detrás
    de `ENABLE_BREAKOUT_STRATEGY=false` en `src/bot.py`/`src/config.py` -
    ver la sección de backtest más abajo para el detalle completo.
15. **Stop a breakeven evaluado (24/09/2026) — RECHAZADO, sin flag de
    producción.** Regla de gestión de salida (mover el SL a entrada+1
    punto al alcanzar 50%/70% de la distancia al TP) sobre la Metodología
    v2, BTC y Oro. En BTC (muestra confiable, 56-61 trades) ambas variantes
    BAJAN el profit factor respecto al baseline (1.80→1.62 al 50%,
    1.80→1.73 al 70%) aunque numéricamente sigan por encima de 1.5 y suban
    el win rate - cortar ganadoras a cambio de una mejora chica en
    aciertos rompe la misma asimetría (ganancia grande/pérdida chica) que
    ya se identificó como el motor del sistema al rechazar el límite de
    tiempo (decisión 10). A diferencia de ETH/Breakout, acá NO se dejó un
    flag de producción (`ENABLE_BREAKOUT_STRATEGY`-style) porque el
    resultado es un rechazo claro y esto requeriría agregar una modificación
    de posición real en `MT5Client` (inexistente hoy) sin ningún caso de uso
    - se prefirió no sumar ese código sin testear en vivo por una función
    que no se va a activar. Queda listo y testeado a nivel de lógica pura
    (`src/breakeven_stop.py`) e integrado en el backtester
    (`run_backtest(enable_breakeven_stop=...)`) para revisitar sin
    reescribir nada si en el futuro cambia el criterio.

## Backtest de validación de la v2 (14/09/2026, antes de desplegar a real)

Corrido sobre los mismos 7 meses de velas H1 (`data/xauusd_h1_raw.csv`,
`data/btcusd_h1_raw.csv`, 5000 velas c/u) usados para validar v1. OJO: estos
CSV (Twelve Data) no traen columna de volumen, así que este backtest **no
ejercita el chequeo de volumen** de la v2 - en vivo el filtro va a estar
activo (MT5 sí entrega `tick_volume`), así que la frecuencia/calidad real
puede diferir de estos números.

Dos corridas por instrumento, ambas con balance inicial $650 y riesgo 2%:
- **Exploratoria** (`is_real_account=False`): todas las señales se toman,
  aunque el lote mínimo fuerce más riesgo del objetivo - sirve para ver la
  calidad cruda de las señales.
- **Realista** (`is_real_account=True`): igual que se comporta el bot en la
  cuenta real - bloquea cualquier señal cuyo SL, al lote mínimo, fuerce más
  del 2% de riesgo. Es el número que importa para decidir si desplegar.

| Instrumento | Señales detectadas | Exploratoria (PF / WR / DD) | **Realista: trades / PF / WR / DD** |
|---|---|---|---|
| XAUUSD | 35 | PF 1.69, WR 40.0%, DD 18.4% | **0 trades** - ninguna de las 35 señales tuvo un SL lo bastante ajustado para entrar en el 2% con el lote mínimo a $650 (riesgo forzado real: 1.5%-17%, mediana bien por encima de 2%) |
| BTCUSD | 28 (exploratoria) / 33 (realista) | PF 2.02, WR 46.4%, DD 7.0% | **33 trades, PF 1.36, WR 39.4%, DD 11.9%, PnL total +$91.68** |

Nota sobre el conteo de BTCUSD (28 vs 33 trades): no es un error - cuando el
backtest bloquea una señal, el motor queda libre para detectar una señal
*distinta* en la vela siguiente (en la corrida exploratoria esa vela
hubiera estado "ocupada" por el trade bloqueado, que ahí sí se tomaba). Es
un efecto conocido del motor de backtest de una sola posición a la vez, no
un bug de la estrategia.

**Conclusión para desplegar:**
- **Oro se puede dejar activo en el código sin ningún riesgo** - la regla
  dinámica simplemente no va a dejarlo operar mientras el capital sea este
  (¿$650?). No es una falla, es la protección de capital funcionando como
  se diseñó. Recién va a empezar a tomar señales cuando el capital crezca
  lo suficiente (ya sea por depósitos o por ganancias de BTC).
- **BTC sigue siendo el motor real del bot** con este capital: PF 1.36 en
  el escenario realista (comparable al 1.39 que ya había dado v1 el
  10/09/2026 - la v2 no muestra una mejora dramática en este backtest
  puntual, aunque las 2 primeras operaciones reales con v2 fueron ambas TP).
  **Superado el 20/09/2026: con RSI 35/65 el PF realista sube a 1.88 -
  ver "Backtest del umbral de RSI relajado" más abajo, ese es el número
  vigente.** Drawdown máximo historico bajo (11.9% sobre $650), riesgo por operación
  acotado.

## Backtest del límite de tiempo máximo (17/09/2026, seccion 6.1) — RECHAZADO

Corrido sobre BTCUSD, mismos 7 meses de H1, $654.77, riesgo 2%, modo
realista (`is_real_account=True`, bloqueando exceso de riesgo igual que la
cuenta real):

| Configuración | Trades | Win rate | Profit factor | PnL total | % cerrados por tiempo |
|---|---|---|---|---|---|
| **Sin límite (actual)** | 36 | 44.4% | **1.73** | **+$194.24** | — |
| 4hs (stall 0.5x ATR) | 42 | 52.4% | 1.37 | +$44.67 | 79% |
| 4hs (stall 0.15x ATR, más laxo) | 42 | 50.0% | 1.35 | +$41.99 | 79% |
| 8hs | 35 | 48.6% | 1.09 | +$15.28 | 60% |
| 12hs | 34 | 47.1% | 1.07 | +$13.84 | 50% |
| 24hs | 39 | 46.2% | 1.43 | +$113.00 | 23% |

(Nota: esta corrida usó el umbral de RSI 30/70 vigente en ese momento. El
20/09/2026 el default cambió a 35/65 - ver sección de abajo -, así que
estos números de "sin límite" ya no reflejan la configuración actual del
bot, aunque la conclusión sobre el límite de tiempo en sí no se revalidó
con el nuevo umbral.)

## Backtest del umbral de RSI relajado (20/09/2026) — ACEPTADO

El usuario preguntó si el filtro de entrada (RSI extremo real <30/>70 +
vela de rechazo) era demasiado estricto. Se probaron 4 variantes sobre los
mismos 7 meses de H1, $654.77, riesgo 2%, modo realista (bloqueo de riesgo
real activo):

| Instrumento | Variante | Señales generadas | Trades reales | Win rate | Profit factor | PnL total | Drawdown |
|---|---|---|---|---|---|---|---|
| XAUUSD | Baseline (RSI 30/70 + rechazo) | 58 | 0 | — | — | $0 | — |
| XAUUSD | A (RSI 30/70, sin rechazo) | 433 | 4 | 25.0% | 0.53 | -$17.88 | 5.8% |
| XAUUSD | **B (RSI 35/65 + rechazo)** | 77 | 2 | 50.0% | 2.36 | +$16.12 | 1.8% |
| XAUUSD | C (RSI 35/65, sin rechazo) | 689 | 8 | 37.5% | 1.32 | +$17.64 | 6.9% |
| BTCUSD | Baseline (RSI 30/70 + rechazo) | 67 | 36 | 44.4% | 1.73 | +$194.24 | 6.8% |
| BTCUSD | A (RSI 30/70, sin rechazo) | 487 | 91 | 36.3% | 1.09 | +$62.88 | 31.0% |
| BTCUSD | **B (RSI 35/65 + rechazo)** | 118 | 59 | **47.5%** | **1.88** | **+$414.93** | 7.6% |
| BTCUSD | C (RSI 35/65, sin rechazo) | 886 | 115 | 35.7% | 1.04 | +$43.42 | 23.3% |

En Oro la muestra es demasiado chica en las 4 variantes (0-8 trades) para
concluir nada - el cuello de botella sigue siendo el capital (sección 3.2),
no el criterio de entrada.

En BTC (muestra de 36-118 trades, más confiable), la Variante B es la
única que mejora profit factor Y win rate Y PnL a la vez, sin empeorar el
drawdown de forma relevante - algo que no había pasado en ningún otro
experimento de ajuste (el límite de tiempo, arriba, empeoraba todo).
Validado además con un split del período en dos mitades independientes
(2500 velas c/u):

| | Baseline 1ra mitad | B 1ra mitad | Baseline 2da mitad | B 2da mitad |
|---|---|---|---|---|
| Trades | 19 | 28 | 16 | 29 |
| Win rate | 42.1% | 46.4% | 43.8% | 48.3% |
| PF | 1.75 | 1.72 | 1.51 | 1.59 |
| PnL | $99.40 | $141.73 | $62.98 | $131.71 |

Win rate y PnL mejoran en las dos mitades por separado; el PF empata en la
primera mitad y mejora en la segunda (nunca empeora) - no parece sobreajuste
a una racha puntual.

**Sacar la vela de rechazo (variantes A y C) es claramente peor** en
cualquier combinación de RSI: el drawdown se dispara a 23-31% (vs 6-8% con
la vela exigida) y el profit factor cae a ~1.0-1.1. La vela de rechazo
evita entrar varias veces sobre el mismo movimiento sin esperar un giro
limpio - se mantiene sin cambios.

**Decisión: se acepta la Variante B.** `rsi_oversold`/`rsi_overbought`
pasan de 30.0/70.0 a 35.0/65.0 por defecto en `StructuralPullbackStrategy`
(`src/strategies/structural_pullback.py`), la vela de rechazo se mantiene
intacta. Confirmado corriendo `scripts/backtest_from_csv.py` con el código
de producción ya actualizado - los números coinciden exacto con la tabla
de arriba.

Ningún umbral probado mejora el resultado sin límite, y no hay una relación
monotónica con las horas (8-12hs da peor resultado que 4hs). En la mayoría
de los cierres forzados, la operación todavía no había llegado a TP ni a
SL - simplemente porque muchas operaciones de este sistema tardan más de
4-12hs en resolverse de forma normal. Cortarlas ahí elimina justo las
ganancias grandes que sostienen la asimetría del sistema (ver sección 9 del
registro: ganancia promedio TP ~$48 vs pérdida promedio SL ~$9).
**Conclusión: no se activa.** Si en el futuro se quiere revisitar (por
ejemplo si cambia el perfil de operaciones o el usuario lo pide de nuevo),
el código está listo en `src/time_exit.py` + `run_backtest(enable_time_exit=...)`
en `src/backtester.py` - hay que volver a correr el backtest antes de
prender `ENABLE_TIME_EXIT=true`, no asumir que sigue siendo mala idea sin
revalidar contra datos más recientes.

## Fix de niveles obsoletos (22/09/2026) — sin regresión

Revalidado con el mismo backtest estándar ($654.77, riesgo 2%, modo real)
sobre los CSV históricos de siempre - los números no se movieron ni un
centavo respecto al benchmark de la sección anterior (XAUUSD 2 trades PF
2.36; BTCUSD 59 trades PF 1.88, WR 47.5%). Es el resultado esperado: esos
CSV usan los símbolos `XAUUSD`/`BTCUSD` (sin la "m"), que nunca coinciden
con las claves `XAUUSDm`/`BTCUSDm` de `config/levels.json` - esos
backtests ya corrían sobre fractales puros antes del fix, así que el
cambio (manual + fractal combinados) no les afecta. No tiene sentido
backtestear el nivel manual nuevo de BTC (82046.15) contra el histórico
Feb-Sept, porque ese nivel es una lectura del gráfico de HOY (22/09), no
algo que haya sido relevante en ese período pasado - su rol es
complementar los fractales en vivo, no algo backtesteable contra datos
viejos.

## Evaluación de ETH como tercer símbolo (23/09/2026) — código listo, APAGADO

El usuario pidió evaluar sumar `ETHUSDm` con exactamente los mismos
parámetros ya validados de BTC (RSI 35/65, vela de rechazo obligatoria,
nivel técnico manual ∪ fractal, riesgo 2%, ajuste por lote no por SL) -
sin modificar ninguna regla, solo correr el backtest y decidir si conviene
activarlo.

**Datos**: se descargaron 5000 velas H1 de ETH/USD (Twelve Data, mismo
proveedor que BTC/Oro) para el mismo período de 7 meses
(13/02/2026-10/09/2026) - `data/ethusd_h1_raw.csv` (gitignored como el
resto de `data/`, se puede volver a generar).

**Resultado** (balance real $746.24, riesgo 2%, `StructuralPullbackStrategy`
sin ningún parámetro modificado):

| Modo | Trades | Win rate | Profit factor | PnL total | Drawdown |
|---|---|---|---|---|---|
| Lote fijo 1.0 (calidad de señal pura) | 50 | 36.0% | 1.44 | +$547.69 | 3.9% |
| Riesgo 2% real (exploratorio = real, ver nota) | 50 | 36.0% | **1.09** | +$47.52 | **23.3%** |

Comparado contra el benchmark vigente de BTC (RSI 35/65, mismo backtest):
**PF 1.88, WR 47.5%, DD 7.6%**. ETH queda claramente por debajo en las tres
métricas, y el drawdown en modo riesgo real (23.3%) es más de 3 veces el de
BTC - un nivel de drawdown que en el pasado (backtest del límite de tiempo,
sección de arriba) ya se asoció con configuraciones descartadas por el
usuario.

**Nota sobre el modo "real" = "exploratorio" (sin diferencia):** a
diferencia de Oro, el filtro de capital de la sección 3.2 **no bloqueó
ninguna de las 50 señales** de ETH (`--is-real-account` dio exactamente el
mismo resultado que sin el flag). Con los specs de contrato asumidos para
ETH (ver advertencia abajo), el SL técnico en Ethereum nunca fuerza más
riesgo del objetivo al lote mínimo con este capital - la dinámica opuesta a
Oro, donde el filtro bloqueaba el 97% de las señales.

**ADVERTENCIA pendiente de verificar**: los parámetros `pip_size=0.01` /
`pip_value_per_lot=0.01` usados para ETH en este backtest son una
**suposición** (copiados de la convención de BTC en Exness: contrato de 1
unidad, 2 decimales), **no verificados contra el Market Watch real de
`ETHUSDm`** como sí se hizo para XAUUSDm/BTCUSDm (ver decisión 3). Si el
contrato real de ETH en la cuenta tiene otro tamaño o `tick_value`, tanto
el profit factor en modo riesgo real como sobre todo el drawdown (23.3%,
la métrica más sensible al sizing) podrían cambiar - los 50 trades, el
36.0% de win rate y el PF 1.44 a lote fijo sí son robustos a este supuesto,
porque no dependen de la conversión a dólares por punto.

**Decisión: NO se activa.** El propio criterio que fijó el usuario para
activarlo (profit factor > 1.5, drawdown no mucho mayor al de BTC) no se
cumple - PF 1.09 y DD 23.3% quedan lejos en ambos sentidos. Se deja el
código preparado pero inerte, mismo patrón que el límite de tiempo
(sección de arriba):
- `src/bot.py`: constante `ETHUSD_SYMBOL = "ETHUSDm"` y
  `build_strategies(config)` agrega el tercer `StructuralPullbackStrategy`
  solo si `config.enable_eth` es `True`.
- `src/config.py`: nuevo campo `AppConfig.enable_eth`, leído de
  `ENABLE_ETH` (default `false`).
- `.env.example`: `ENABLE_ETH=false` documentado.
- `config/levels.json`: clave `ETHUSDm` agregada (vacía por ahora - sin
  niveles manuales cargados, el bot igual detecta fractales automáticos si
  se llega a activar).

Si en el futuro se quiere reconsiderar: primero verificar las specs reales
de `ETHUSDm` en el Market Watch de la cuenta (no asumir 0.01/0.01), volver
a correr `scripts/backtest_from_csv.py` con esas specs confirmadas, y
recién ahí evaluar si conviene prender `ENABLE_ETH=true` - no activar solo
porque haya pasado tiempo o cambiado el capital, sin revalidar.

## Estrategia de ruptura de consolidación (23/09/2026) — código listo, RECHAZADA

El usuario pidió evaluar un sistema SEPARADO de la Metodología v2 (no la
reemplaza ni la toca): operar la ruptura de un rango de consolidación en
vez de esperar un pullback sobre un nivel estructural. Reglas pedidas, sin
margen de interpretación propia:

1. Consolidación: ATR promedio de las últimas 10-14 velas por debajo de su
   propio promedio de las últimas 50.
2. Señal: vela cierra por fuera del rango + volumen de esa vela ≥1.5x el
   promedio de volumen de las últimas 20 velas.
3. Confirmación: la vela siguiente cierra en la misma dirección, sin volver
   a meterse dentro del rango roto.
4. SL en el borde opuesto del rango roto. TP a un mínimo de 2:1 (también se
   evaluó una variante con trailing stop desde 1R, ver más abajo).

Implementado en `src/strategies/breakout.py` (`BreakoutStrategy`, 8 tests en
`tests/test_breakout.py`) - mismo patrón de interfaz que
`StructuralPullbackStrategy`, sin tocar ese archivo.

**Datos**: mismos 5000 velas H1 de BTC ya usadas para todo el resto de los
backtests (`data/btcusd_h1_raw.csv`), mismo período de 7 meses. El usuario
pidió evaluar esto solo sobre BTC (no Oro/ETH).

**Resultado** (mismos parámetros default, sin ajustar nada a mano):

| Modo | Trades | Win rate | Profit factor | PnL total | Drawdown |
|---|---|---|---|---|---|
| Lote fijo 1.0 (calidad de señal pura, TP fijo 2R) | 47 | 31.9% | **1.06** | +$3108.67* | **76.3%*** |
| Riesgo 2% sobre capital TOTAL ($746.24), real (TP fijo 2R) | 44 | 34.1% | 1.11 | +$47.74 | 13.8% |
| Trailing stop desde 1R (lote fijo, evaluado a pedido) | 62 | 53.2% | **0.79** | -$8913.32* | — |

(*PnL/DD en USD del "lote fijo" no son realistas en magnitud - mismo
disclaimer que en todos los backtests anteriores, sirven para aislar
calidad de señal, no para leer el dólar. El profit factor y el win rate sí
son comparables directamente.)

Comparado contra el criterio que el propio usuario fijó (PF > 1.5, mismo
que se usó para rechazar ETH): **ningún modo lo alcanza, ni por asomo**. El
trailing desde 1R, lejos de mejorar las cosas, las empeora (PF 0.79 vs
1.06) - más operaciones ganadoras chicas (WR sube a 53.2%) pero las
perdedoras (que siguen siendo -1R completo cuando el precio nunca llega a
activar el trailing) se comen la ganancia. La causa de fondo no es el
esquema de salida (2R fijo vs. trailing) sino la calidad de la señal de
entrada misma - un win rate de 32-53% con un R:R de 2:1 apenas empata o
pierde, no hay margen.

**Bucket de capital (pregunta explícita del usuario: "¿es ejecutable con
el lote mínimo de BTC o el filtro de capital lo bloquea, igual que pasó
con Oro?"): la respuesta es SÍ, se bloquea, casi exactamente igual que
Oro.** Con el bucket de 15% del capital real ($746.24 → $111.94) y riesgo
3% de ese bucket ($3.36 objetivo por operación), el lote mínimo de BTC
(0.01 lotes) fuerza entre 4.2% y 46.1% de riesgo real en la enorme mayoría
de las 47 señales - muy por encima del 3% objetivo. En modo real
(bloqueando como bloquearía la cuenta real) solo pasan **2 de 47 señales**,
y las dos resultaron en pérdida (profit factor 0.00). El motivo es
aritmético, no una casualidad: el rango de precio de BTC (miles de
dólares) hace que hasta un SL "ajustado" en términos de la estrategia siga
siendo grande en dólares, y un bucket de ~$112 con lote mínimo de 0.01 BTC
no tiene margen para absorber eso al 3% de riesgo - la misma dinámica que
ya se documentó para Oro con el capital total (sección 3.2), aplicada acá
a un bucket chico en vez de a todo el capital.

**Decisión: NO se activa.** Falla en las dos preguntas que el usuario pidió
confirmar antes de considerarlo: la calidad de señal no llega al profit
factor mínimo (1.06-1.11 vs. 1.5 exigido) y el esquema de capital pedido no
es ejecutable con el lote mínimo de BTC (2 de 47 señales pasan, ambas
perdedoras). Se deja el código preparado pero inerte, mismo patrón que ETH
y el límite de tiempo:
- `src/strategies/breakout.py`: `BreakoutStrategy`, testeada, sin tocar
  `structural_pullback.py`.
- `src/bot.py`: `build_strategies(config)` agrega `BreakoutStrategy` sobre
  BTC solo si `config.enable_breakout_strategy` es `True`; `iterate()`
  arma un `RiskManager` y balance separados (el bucket) solo para esta
  estrategia cuando corresponde (rama `isinstance(strategy, BreakoutStrategy)`),
  sin tocar el sizing de la Metodología v2. El límite de tiempo (sección
  6.1) queda explícitamente afuera de esta estrategia (no tiene
  `rsi_period`), para que activar `ENABLE_TIME_EXIT` y
  `ENABLE_BREAKOUT_STRATEGY` a la vez no rompa nada.
- `src/config.py`: `AppConfig.enable_breakout_strategy`,
  `breakout_bucket_pct` (15.0 default), `breakout_risk_per_trade_pct` (3.0
  default).
- `.env.example`: `ENABLE_BREAKOUT_STRATEGY=false`,
  `BREAKOUT_BUCKET_PCT=15.0`, `BREAKOUT_RISK_PER_TRADE_PCT=3.0`.

Si en el futuro se quiere reconsiderar: el problema de fondo es la calidad
de la señal de entrada (32-53% de acierto no alcanza con 2:1), no un
detalle de implementación - antes de tocar el código, repensar el criterio
de entrada (por ejemplo, un filtro de tendencia de marco mayor que filtre
rupturas en contra de la tendencia dominante) y volver a correr el
backtest completo, no solo ajustar el bucket de capital.

## Backtest del stop a breakeven (24/09/2026) — RECHAZADO

El usuario pidió backtestear una regla de gestión (no de entrada, no toca
la Metodología v2): cuando una operación abierta alcanza X% de la distancia
al TP, mover el SL al precio de entrada + 1 punto (cubre spread/comisión).
Probar 50% y 70%, sobre BTC y Oro, mismos 7 meses de siempre, comparando
contra el benchmark vigente.

Implementado en `src/breakeven_stop.py` (`breakeven_stop_price`, 6 tests en
`tests/test_breakeven_stop.py`) e integrado en `src/backtester.py`
(`run_backtest(enable_breakeven_stop=..., breakeven_trigger_pct=...,
breakeven_buffer=...)`) - el SL se actualiza usando el high/low de cada
vela (no el cierre) para no perderse un toque intra-vela, y nunca se mueve
en contra (solo "sube" para BUY / "baja" para SELL).

**Resultado** (balance real $746.24, riesgo 2%, modo real, buffer 1 punto):

| Instrumento | Variante | Trades | Win rate | Profit factor | Drawdown | Salidas SL / TP / Breakeven |
|---|---|---|---|---|---|---|
| BTCUSD | Baseline (sin regla) | 56 | 48.2% | **1.80** | 8.1% | 29 / 27 / — |
| BTCUSD | Breakeven 50% | 61 | 57.4% | 1.62 | 7.4% | 26 / 21 / 14 |
| BTCUSD | Breakeven 70% | 61 | 50.8% | 1.73 | 8.1% | 30 / 25 / 6 |
| XAUUSD | Baseline (sin regla) | 2 | 50.0% | 2.36 | 1.6% | 1 / 1 / — |
| XAUUSD | Breakeven 50%/70% | 2 | 50.0% | 0.17 | 1.6% | 1 / 0 / 1 |

(Nota: el baseline de BTC acá da 1.80/56 trades en vez del 1.88/59 trades
de referencia porque corre sobre $746.24 en vez de $654.77 - mismo "efecto
conocido del motor de backtest de una sola posición a la vez" ya
documentado antes, no una regresión.)

**En Oro la muestra sigue siendo de 2 trades** (mismo cuello de botella de
capital de siempre) - no da para concluir nada en general, pero sí sirve
para ilustrar el mecanismo sin ambigüedad: se verificó operación por
operación que la lógica es correcta (no es un bug). La operación ganadora
(BUY, TP a +$27.98) tocó el 50% del camino al TP y el SL subió a
entrada+1 punto; el precio revirtió y la cerró ahí, en +$2.00 en vez de
+$27.98 - la otra operación (la perdedora, -$11.87) no cambió. Neto:
+$16.12 → -$9.87.

**En BTC (muestra confiable) el resultado es más sutil que un simple
rechazo por número**: las dos variantes SUBEN el win rate (48.2%→57.4%/
50.8%) y técnicamente el profit factor sigue arriba de 1.5 en ambas (1.62 y
1.73) - el número absoluto que pidió el usuario como criterio ("solo se
activa si PF>1.5") se cumple. Pero comparado contra el benchmark actual
(1.80), **ambas variantes son un retroceso, no una mejora** - cortar
operaciones ganadoras en el 50-70% del camino cambia más aciertos por
ganancias más chicas, la misma asimetría (pocas ganancias grandes
compensan varias pérdidas chicas) que ya se identificó como el motor real
del sistema al rechazar el límite de tiempo (decisión 10) y al aceptar
RSI 35/65 justamente porque ahí SÍ mejoraba todo a la vez. 70% se acerca
más al baseline que 50% (corta menos operaciones prematuramente: 6 vs 14),
pero ninguna de las dos supera lo que ya hay.

**Decisión: NO se activa, en ninguno de los dos umbrales.** El criterio
numérico aislado (PF>1.5) se cumple pero el objetivo real - mejorar sobre
lo que ya funciona - no, así que se aplica el mismo espíritu que en el
resto de las decisiones de este documento (nunca se adoptó un cambio que
sacrifique profit factor a cambio de win rate). A diferencia de ETH y la
estrategia de ruptura, acá no se dejó un flag `ENABLE_BREAKEVEN_STOP` para
producción: activar esto en vivo requeriría agregar una operación de
modificación de posición real a `MT5Client` (no existe hoy, solo
`send_order`/`close_position`) - construir y dejar inerte ese código sin
haberlo probado contra una conexión MT5 real, para una función que dio
rechazo claro, es riesgo sin beneficio. Si se quiere reconsiderar, la
lógica ya está lista y testeada en `src/breakeven_stop.py` +
`run_backtest(enable_breakeven_stop=...)` - alcanza con volver a correr el
backtest con otros umbrales/buffer, no hace falta escribir la regla de
nuevo.

## Timeframe M30 para BTC (24/09/2026) — RECHAZADO

El usuario planteó que 15 días sin ninguna operación (el peor caso del
backtest de 7 meses en H1) es demasiado tiempo, y preguntó si operar en un
timeframe menor (M30/M15) generaría más señales sin cambiar la lógica de
entrada. Se evaluó M30 (mismos parámetros default de
`StructuralPullbackStrategy`, solo cambiando `timeframe="M30"`).

**Primera corrida (3.5 meses, todo lo que daba una sola descarga de Twelve
Data)**: 59 trades, WR 42.4%, PF 1.52, DD 14.8% - más del doble de
frecuencia que H1 (~3.9/semana vs ~2/semana), pero con peor calidad. Un
tercer chat consultado en paralelo por el usuario recomendó, con buen
criterio, no decidir con una muestra tan corta y conseguir más historial
antes de comprometerse - se bajó un segundo tramo de Twelve Data
(`data/btcusd_m30_raw.csv`, 10000 velas, 26/02/2026-24/09/2026, ~7 meses,
igual que el período de referencia de H1) sin necesitar que el usuario
exporte nada de MT5.

**Con los 7 meses completos, la conclusión se invierte**:

| Tramo | Trades | Win rate | Profit factor | Drawdown |
|---|---|---|---|---|
| M30, 1ra mitad (feb-jun) | 51 | 27.5% | **0.75** (perdedor) | 28.1% |
| M30, 2da mitad (jun-sep, la corrida original) | 59 | 42.4% | 1.52 | 14.8% |
| **M30, 7 meses completos** | 111 | 35.1% | **1.04** | **42.3%** |
| H1 (referencia vigente, 7 meses) | 59 | 47.5% | **1.88** | 7.6% |

La muestra corta de 3.5 meses resultó ser justo el tramo favorable, no
representativa del período completo: en la primera mitad M30 pierde plata
(PF 0.75) y el número global cae a 1.04 (casi empate) con un drawdown del
42.3% - más de 5 veces el de H1. Es la misma prueba de consistencia entre
mitades que ya se uso para aceptar RSI 35/65 (mejoraba en las dos mitades)
y ahí es donde M30 falla: una mitad gana, la otra pierde fuerte - señal de
que el "nivel tocado"/RSI extremo en M30 es mucho más ruidoso y menos
estable entre regímenes de mercado que en H1.

**Decisión: NO se activa, ni como bucket separado en paralelo a H1** (la
sugerencia original era justamente condicional a que el PF se sostuviera
arriba de 1.5 con más datos - no se sostiene). No se dejó ningún flag de
producción porque no hace falta código nuevo para reconsiderarlo -
`StructuralPullbackStrategy(symbol=BTCUSD_SYMBOL, timeframe="M30")` ya es
instanciable tal cual con la clase existente; alcanza con volver a correr
`scripts/backtest_from_csv.py` sobre datos de M30 más recientes si en el
futuro se quiere revisar, sin escribir nada nuevo.

**El problema de fondo (15 días de silencio genera desconfianza) no se
resuelve tocando la estrategia** - forzar más frecuencia ya demostró
sistemáticamente empeorar la calidad en este proyecto (RSI sin vela de
rechazo, ETH, Breakout, breakeven, y ahora M30). Se redirigió a mejorar
visibilidad (notificaciones) en su lugar - ver la sección siguiente.

## Notificaciones por mail (24/09/2026)

Como alternativa real al problema de fondo de la sección anterior (no la
frecuencia de operaciones, sino la falta de visibilidad durante un tramo
largo sin señales), se implementaron avisos por mail: apertura de una
operación real, cierre (con el resultado leído del historial de MT5), y
errores inesperados. Usuario confirmó: mail
`juancruzmartin88@gmail.com` para enviar y recibir (no Telegram, no lo
usa), y los tres eventos (apertura, cierre, errores).

**Deliberadamente NO se notifica cada bloqueo por gestión de riesgo** -
sería un mail cada 30 segundos mientras haya una posición manual abierta
(el caso real del 22-24/09/2026, cientos de líneas idénticas en el log) -
puro spam. Solo transiciones de estado reales.

Implementación:
- `src/notifier.py`: `EmailNotifier`, SMTP simple (Gmail por defecto,
  `smtp.gmail.com:587` con STARTTLS) - un fallo al enviar nunca frena el
  trading, solo se loguea (`logger.exception`).
- `src/mt5_client.py`: `ClosedTradeInfo` + `get_closed_trade_info(ticket)`,
  lee `history_deals_get(position=ticket)` y filtra los deals de salida
  (`DEAL_ENTRY_OUT`) para sacar ganancia/pérdida y precio de cierre - no
  depende de que el cierre lo haya hecho el bot (cubre SL/TP del broker
  también).
- `src/bot.py`: `build_notifier(config)` (None si `enable_email_notifications`
  es False); `run()` mantiene `known_tickets: dict[symbol, ticket | None]`
  inicializado con lo que ya esté abierto al arrancar (para no perderse el
  cierre de una posición de una corrida anterior); `_check_position_closed`
  se llama una vez por símbolo único al principio de cada vuelta del loop
  (no por estrategia, para no duplicar si BTC llegara a tener dos
  estrategias activas sobre el mismo símbolo); `iterate()` notifica la
  apertura después de `send_order` y actualiza `known_tickets` con el
  ticket nuevo (solo si no es DRY_RUN); el `except Exception` genérico del
  loop notifica errores, el `except RiskLimitExceeded` (bloqueos
  rutinarios) nunca notifica.
- `src/config.py`: `enable_email_notifications`, `smtp_host`, `smtp_port`,
  `smtp_user`, `smtp_password`, `notify_to_email` - si el flag está en
  `true` pero falta alguna de las tres credenciales, `load_config()`
  tira `ConfigError` explícito en vez de fallar en silencio más tarde.
- `.env.example`: `ENABLE_EMAIL_NOTIFICATIONS=false` por defecto - el
  usuario tiene que generar una "Contraseña de aplicación" de Gmail (no su
  contraseña normal) y cargar `SMTP_USER`/`SMTP_PASSWORD`/`NOTIFY_TO_EMAIL`
  - pasos completos en README ("Notificaciones por mail").
- 13 tests nuevos (`tests/test_bot.py`, `tests/test_notifier.py`) con
  clientes/notifiers falsos - no requieren MT5 ni credenciales SMTP reales,
  así que no se pudo probar el envío real de un mail desde este entorno
  (sin acceso a MT5 ni, probablemente, a SMTP saliente) - la primera prueba
  real la tuvo que hacer el usuario en su PC.
- `scripts/test_email.py` (24/09/2026, agregado después de activar el
  flag): dispara un mail de prueba directo (`notifier.notify_error`) leyendo
  la config real del `.env`, sin esperar a que el bot abra/cierre una
  operación real. Se sumó porque el bot en la cuenta real corre con
  `DRY_RUN=false` (no hay operaciones simuladas que disparen el aviso
  `[SIMULADO]`), así que validar con una operación real hubiera significado
  esperar sin saber si el envío de mails andaba. Uso:
  `python -m scripts.test_email`.

**ACTIVADO Y VALIDADO el 24/09/2026** - el usuario generó su Contraseña de
aplicación de Gmail, cargó `SMTP_USER`/`SMTP_PASSWORD`/`NOTIFY_TO_EMAIL` en
su `.env` real y confirmó que le llegó el mail de prueba disparado por
`scripts/test_email.py`. `ENABLE_EMAIL_NOTIFICATIONS=true` en su `.env` de
producción. Nota para sesiones futuras: la confusión más común al cargar
estas variables es editarlas en `.env.example` (la plantilla, la que trae
el repo) en vez de `.env` (el archivo real, gitignored, específico de la
PC del usuario) - si en algún momento las notificaciones parecen no andar
pero `load_config()` no tira ningún `ConfigError`, lo primero a chequear es
`Get-Content .env | Select-String "ENABLE_EMAIL_NOTIFICATIONS"` para
confirmar que la variable realmente está en el archivo correcto.

## Evaluación de Plata (XAG/USD) como tercer instrumento (24/09/2026) — RECHAZADA

El usuario pidió evaluar `XAGUSDm` con exactamente los mismos parámetros ya
validados de BTC/Oro (Metodología v2 completa: RSI 35/65, giro confirmado,
vela de rechazo, nivel técnico manual ∪ fractal, riesgo 2% por operación),
sobre el mismo período de 7 meses de referencia, comparando contra el
benchmark de BTC (PF 1.88, DD 7.6%) y revisando en particular cómo le pega
el filtro de capital de la sección 3.2 (el mismo que tiene dormido a Oro).

**Datos**: Twelve Data no deja bajar `XAG/USD` con el plan conectado
actualmente ("requiere plan Grow o Venture") - a diferencia de Oro y BTC,
que sí están disponibles. Se resolvió pidiéndole al usuario que exportara
el histórico directo desde su MT5 (`Symbols → Bars → XAGUSDm → H1 →
Export`, cubriendo 2025-01-01 a hoy) - 10.233 velas H1 reales del broker,
de las cuales se recortaron las 3.392 que caen en el mismo período de 7
meses usado de referencia para BTC/Oro/ETH (13/02/2026-10/09/2026). Menos
velas que las 5.000 de BTC porque Plata no opera 24/7 (igual que Oro).
CSV gitignored en `data/xagusd_h1_raw.csv`, se puede regenerar pidiendo el
mismo export.

**Specs de contrato verificadas** (a diferencia de ETH, que quedó con una
suposición sin confirmar): la ventana "Symbols" de MT5 mostró la
especificación real de `XAGUSDm` - Categoría Metals, 3 decimales,
**contract size 5.000 XAG** (5.000 onzas por lote), margen en XAG,
ganancia en USD. Traducido a los parámetros del backtester:
`pip_size=0.001`, `pip_value_per_lot=5.0` (5.000 oz × $0.001).

**Resultado** (balance real $715.24, riesgo 2%, `StructuralPullbackStrategy`
sin ningún parámetro modificado, niveles manuales vacíos para `XAGUSDm` en
`config/levels.json` → fractales puros):

| Modo | Trades | Win rate | Profit factor | Drawdown |
|---|---|---|---|---|
| Lote fijo 1.0 (calidad de señal pura) | 25 | 16.0% | **0.24** | 1731.9%* |
| Riesgo 2% real (exploratorio, sin filtro de capital) | 25 | 16.0% | **0.24** | 242.1%* |
| Riesgo 2% real (**realista**, con filtro sección 3.2) | **0** | — | 0.00 | — |

(*El drawdown de estas dos filas no es literal - el motor del backtest no
frena en cuenta negativa, el balance simulado llegó a valores negativos
varias veces en el log de detalle. Solo ilustra que, sin el filtro de
capital, la cuenta real se hubiera destruido varias veces sobre este
período - mismo disclaimer que en todos los backtests de "lote fijo"
anteriores, pero acá aplica también a la fila de riesgo real porque la
señal es mala independientemente del sizing.)

Comparado contra el benchmark vigente de BTC (**PF 1.88, WR 47.5%, DD
7.6%**): Plata queda muy por debajo en las tres métricas, sin punto de
comparación cercano - ni siquiera se acerca al nivel de ETH (PF 1.09) o
Breakout (PF 1.06-1.11), que ya habían sido rechazados.

**Sobre el filtro de capital de la sección 3.2 (pregunta explícita del
usuario)**: le pega **igual o peor que a Oro** - las 25 señales quedaron
bloqueadas en modo realista, 0 pasan. El SL técnico observado en las 25
señales forzaba entre 3.4% y 692% de riesgo real al lote mínimo (mediana
bien por encima del 2% objetivo) - mismo problema estructural que Oro: el
contrato de 5.000 onzas por lote hace que hasta un SL "ajustado" en
términos de la estrategia sea grande en dólares al lote mínimo del broker.

**La diferencia clave con Oro, que hace que esto no sea "dormir el código
esperando más capital" como con Oro**: en Oro, la calidad de señal en modo
exploratorio ya era buena desde el principio (PF 1.69 en el backtest del
14/09/2026) - el único obstáculo era el capital, y se espera que se
resuelva solo cuando la cuenta crezca. **En Plata, ni sacando el filtro de
capital funciona** (PF 0.24, WR 16% en modo exploratorio) - el problema no
es solo el lote mínimo, la señal misma no es buena en H1 con estos
parámetros. Con solo 25 trades la muestra es chica (similar a ETH/Breakout),
pero un PF de 0.24 y WR de 16% es una diferencia demasiado grande para
necesitar una validación por mitades como se hizo con RSI 35/65 - no es un
caso límite.

**Decisión: NO se activa.** No cumple el criterio del usuario (PF > 1.5 sin
ser una regresión) por un margen amplio, y además falla la pregunta sobre
el filtro de capital (0 de 25 señales ejecutables en cuenta real, igual que
Oro). A diferencia de ETH y Breakout, **no se agregó ningún flag de
producción** (`ENABLE_SILVER`-style) porque no hace falta código nuevo para
reconsiderarlo - `StructuralPullbackStrategy(symbol="XAGUSDm",
timeframe="H1")` ya es instanciable tal cual con la clase existente (mismo
patrón que se usó para descartar M30). Se agregó la clave `XAGUSDm: []`
(vacía) a `config/levels.json` para que el backtest pudiera correr con
fallback a fractales, sin niveles manuales cargados.

Si en el futuro se quiere reconsiderar: el problema de fondo es la calidad
de la señal en Plata H1 (WR 16%), no el capital ni el sizing - antes de
volver a intentarlo, pensar si tiene sentido un filtro o parámetro
específico para Plata (por ejemplo, un ATR mínimo o un timeframe distinto)
en vez de asumir que los mismos parámetros de BTC/Oro van a funcionar
igual de bien en un tercer instrumento con dinámica de precio distinta.

## Diferencia entre operaciones manuales y detección del bot en Oro (24/09/2026)

El usuario tomó 2 operaciones manuales en `XAUUSDm` esa semana (Buy Limit,
SL chico dentro de lo que permite el filtro de capital) y preguntó si el
bot había visto esas mismas señales (RSI real + vela de rechazo + nivel
estructural) y las descartó, o directamente no las detectó, y por qué:

- 23/09: Buy Limit 4.284, SL 4.273 (11 puntos)
- 24/09 (mañana): Buy Limit 4.256, SL 4.248 (8 puntos)

**Diagnóstico**: no hay acceso a `logs/bot.log` de esas fechas desde este
sandbox (vive solo en la PC del usuario), así que en vez de especular se
reprodujo `StructuralPullbackStrategy._analyze()` (la lógica exacta de
producción) vela por vela contra velas H1 reales de Oro del 22 al 24/09
(Twelve Data, spot XAU/USD - posible pequeño desvío de precio/huso horario
de vela contra el feed real de Exness, pero suficiente para diagnóstico).
El bot sí generó señales BUY en la ventana (7 en total, 14-25/09), pero
ninguna coincide con las dos operaciones puntuales del usuario. Causa
distinta para cada una:

- **24/09 - timing exacto del cierre de vela**: hubo DOS velas de rechazo
  válidas (martillo) a las 04:00 y 05:00 (UTC) que el bot descartó porque
  la vela de confirmación siguiente cerró bajista en vez de alcista. Recién
  a las 08:00 se dio el par martillo+confirmación alcista - para entonces
  el precio ya estaba en 4.289 (no 4.256), con RSI en 36.4 (recién cruzando
  el umbral). El bot sí llegó a generar una señal BUY en esa vela, pero muy
  distinta a la del usuario: entrada 4.289, SL 4.264 (25.5 puntos) - un
  stop mucho más ancho que los 8 puntos manuales, porque
  `_calculate_stop_loss` usa el mínimo de toda la ventana de pullback
  (8 velas) menos margen de ATR, no el punto técnico más ajustado posible.
  Esta es la misma razón estructural por la que el filtro de capital
  (sección 3.2) bloquea tanto a Oro: los SL del bot son sistemáticamente
  más anchos que un SL manual calibrado a mano para entrar bajo el filtro.
- **23/09 - vela de rechazo más estricta que la lectura visual**: el precio
  sí tocó una zona cercana a 4.284 (low 4.281) con RSI en 26.3 (sobreventa
  clara) a las 23:00 UTC, pero la vela previa (22:00, la vela de rechazo
  que evalúa el bot) tiene un cuerpo bajista grande - geométricamente no
  cumple el test de martillo (`is_hammer`: mecha ≥1.5x el cuerpo Y la mecha
  opuesta ≤30% del rango), la clasificó como estrella fugaz (patrón
  bajista). Como el patrón no calificó, la condición 4 de la Metodología v2
  nunca se evaluó para BUY en ese punto, sin importar que el nivel y el RSI
  sí estuvieran en zona.
- **Detección de niveles**: no fue el problema en ninguno de los dos casos
  - siempre hubo un nivel (manual o fractal) cerca del precio en las velas
  relevantes.
- **Diferencia estructural de fondo (aplica a ambos casos)**: el usuario
  entró con **Buy Limit** (orden pendiente esperando que el precio baje al
  nivel). El bot **nunca coloca órdenes pendientes** - solo manda mercado
  en la vela ya cerrada (decisión de arquitectura del 14/09, ver decisión
  7). Aunque el bot reconociera exactamente el mismo setup, el mecanismo de
  entrada (precio, timing, y por lo tanto el SL resultante) iba a diferir
  siempre de una Buy Limit manual.

**No se tocó ningún parámetro de la estrategia** - el usuario aclaró
explícitamente que no estaba pidiendo aflojar el filtro de capital, sino
entender si había una diferencia real de detección. La respuesta es sí,
por dos motivos puntuales y distintos (timing de confirmación en un caso,
estrictez geométrica de la vela de rechazo en el otro), más una diferencia
de fondo en el tipo de orden que aplica siempre. Queda documentado acá para
no tener que re-investigar si vuelve a surgir la misma pregunta.

## Evaluación del straddle de reapertura semanal (27/09/2026) — código listo, esperando datos reales

Idea propuesta por el usuario (consultada en paralelo con otro chat),
sistema SEPARADO de la Metodología v2, solo para XAUUSD: en la primera vela
H1 tras la reapertura semanal del mercado, colocar Buy Stop sobre el máximo
de esa vela y Sell Stop bajo el mínimo (straddle/OCO - la que se dispara
primero cancela la otra), SL en el extremo opuesto de la misma vela, TP a
1x o 1.5x el riesgo (no un nivel estructural), con un filtro de rango
mínimo (la vela de reapertura tiene que superar un ATR de referencia, para
descartar reaperturas sin información real). Protocolo de validación
pedido explícitamente: 20-30 reaperturas históricas de XAUUSD, profit
factor > 1.5, y split de la muestra en dos mitades para chequear
consistencia - mismo estándar que se usó para aceptar RSI 35/65 y rechazar
M30/Plata.

**Implementado y testeado** (lógica pura, sin depender de datos reales
todavía):
- `src/weekly_gap.py`: `find_reopen_indices` (detecta velas que arrancan
  tras un hueco de horario real ≥N horas - la reapertura semanal genuina),
  `simulate_straddle` (simula las dos pendientes, cuál se activa primero,
  SL/TP en múltiplos de riesgo R - no en dólares, porque el mecanismo de
  dos órdenes pendientes simultáneas no encaja en `src/backtester.py`, que
  asume una sola estrategia por vela), `summarize` (profit factor y win
  rate en R). 8 tests en `tests/test_weekly_gap.py`, con velas sintéticas -
  cubren detección de huecos, filtro de rango, resolución BUY/SELL,
  ambigüedad de "las dos pendientes se tocan en la misma vela" (se resuelve
  aproximando por cuál nivel está más cerca del open de esa vela), y "no se
  resuelve dentro de la ventana".
- `scripts/backtest_weekly_gap.py`: corre `weekly_gap.py` sobre un CSV
  histórico real, con el mismo split de mitades que pide el protocolo.
  Acepta el formato de export de MT5 (`Symbols → Bars → Export`) o un CSV
  estándar con columna de tiempo única.

**BLOQUEADO por datos, no por código**: `find_reopen_indices` necesita
huecos de horario GENUINOS entre el cierre del viernes y la reapertura -
verificado el 27/09/2026 que **Twelve Data rellena el cierre de mercado de
XAU/USD con un precio casi congelado** (ejemplo real: sábado 08:00 a
domingo 04:00, precio moviéndose menos de 0.3 puntos en >30hs, sin ningún
hueco de horario en los timestamps) en vez de dejar el hueco real o
reflejar el salto genuino de reapertura. Correr esta estrategia sobre ese
dataset daría un falso negativo (o un resultado sin sentido) - la premisa
entera depende de medir el gap real, que ese feed no tiene. `data/xauusd_h1_raw.csv`
(el CSV de Twelve Data ya usado para todos los demás backtests de este
proyecto) **no sirve para esta evaluación en particular**, aunque sí sigue
sirviendo para todo lo demás (Metodología v2, ETH, Breakout, M30).

El pipeline completo se validó igual, de punta a punta, corriendo
`scripts/backtest_weekly_gap.py` sobre el export real de MT5 de
`XAGUSDm` que ya se había pedido para la evaluación de Plata (ese sí tiene
huecos de horario reales) - detectó 92 reaperturas en ~20 meses, 43
pasaron el filtro de rango, con timestamps de reapertura sensatos
(22-23hs UTC, domingo a la noche). Esto confirma que el código funciona
correctamente - no es el resultado que responde la pregunta del usuario
(era Plata, no Oro, y el usuario no pidió evaluar Plata para esto), solo
una prueba de que el mecanismo está bien armado antes de correrlo con los
datos que sí importan.

**ACTUALIZACIÓN 27/09/2026 - datos reales recibidos y validados.** El
usuario exportó `XAUUSDm` H1 real desde su MT5 (21 meses, 2025-01-01 a
2026-09-25, 10.266 velas) - a diferencia de Twelve Data, tiene huecos de
horario genuinos en los cierres de fin de semana.

**Resultado principal** (`--tp-r-multiple=1.0 --min-range-atr-mult=1.0`,
la configuración por defecto del script):

| Variante | Trades | Win rate | Profit factor | 1ra mitad | 2da mitad |
|---|---|---|---|---|---|
| **TP 1x el riesgo** | 55 | 65.5% | **1.89** | PF 2.00 (27) | PF 1.80 (28) |
| TP 1.5x el riesgo | 55 | 52.7% | 1.67 | PF 1.88 (27) | PF 1.50 (28, límite) |
| Sin filtro de rango (control) | 91 | 58.2% | 1.39 | — | — |

**TP 1x es la variante más sólida y la que se acepta como referencia** -
cumple PF > 1.5 en las dos mitades, consistente ante distintos períodos de
ATR de referencia (50/100/200 velas, PF entre 1.79 y 1.89 en los tres
casos). Sacar el filtro de rango mínimo (tomar todas las reaperturas sin
filtrar) hace caer el PF a 1.39 - confirma que el filtro que pidió el
usuario ("descartar aperturas chatas") es lo que sostiene el resultado, no
es cosmético. Es el resultado con profit factor más alto y más consistente
de todo este documento (por encima de RSI 35/65 en BTC).

**Los 3 puntos de ejecución pendientes de la propuesta original**:

1. **¿Exness permite OCO?** No es una pregunta de permiso del broker -
   MetaTrader 5 no tiene un tipo de orden "OCO" nativo en ningún broker (los
   tipos base son Buy/Sell Stop/Limit). El comportamiento OCO siempre se
   logra con un programa externo (EA o, en este caso, el propio bot en
   Python) que vigila las dos pendientes y cancela la que no se activó -
   es el mismo patrón que ya usa el bot con `mt5.order_send`, no requiere
   nada especial de Exness.
2. **Spread en el momento de reapertura**: comparado a nivel de vela H1
   (columna `<SPREAD>` del export de MT5), el spread promedio en las 92
   velas de reapertura (198.5 puntos) es prácticamente igual al spread
   promedio normal (197.0 puntos) - no hay ensanchamiento sistemático
   grande a ese nivel de agregación. Salvedad importante: esto es un
   promedio por vela completa (probablemente muestreado al cierre), no
   necesariamente el pico de los primeros segundos/minutos de la
   reapertura, que es cuando más importa - recomendable confirmarlo
   observando en vivo un domingo a la noche antes de confiar en esto al
   100%.
3. **Traducción a dólares reales vía `RiskManager` (balance real $715.24,
   riesgo 2%, `pip_size=0.01`/`pip_value_per_lot=1.0` de Oro) - el hallazgo
   más importante de los tres**: el filtro de capital de la sección 3.2
   **bloquea 43 de las 55 señales (78%)** - el SL de este sistema (extremo
   opuesto de toda la vela de reapertura) suele ser bastante ancho
   (11-120+ puntos), y con este capital Oro solo admite SL ≤ ~13-15 puntos
   al lote mínimo. Es el mismo cuello de botella estructural que ya tiene
   Oro en la Metodología v2 normal (sección 3.2) - no es una falla del
   concepto nuevo, es la misma protección de capital de siempre.

**Aclaración importante sobre qué muestra respalda cada número (el usuario
preguntó esto explícitamente el 27/09/2026, antes de dar la evaluación por
cerrada)**: el **PF 1.89 es sobre las 55 señales que pasan el filtro de
rango - la muestra histórica completa de setups válidos, ANTES del filtro
de capital** - ese es el número que importa para juzgar la calidad de la
señal en sí. El filtro de capital determina, aparte, cuántas de esas 55
serían ejecutables *hoy* con el capital actual: **solo 12**, con PF 1.09.
Split de mitades sobre esas 12 (pedido explícitamente, mismo estándar que
siempre): 1ra mitad (6 trades) PF 2.18, 2da mitad (6 trades) **PF 0.58** -
se da vuelta por completo, confirma que n=12 es ruido puro, no dice nada en
ningún sentido. Dato adicional: las 12 ejecutables quedan **todas
concentradas entre enero y septiembre de 2025** (ninguna en el último año) -
a medida que Oro subió de ~$2.600 a ~$4.800 durante el período, el rango
típico de la vela de reapertura (y por lo tanto el SL de esta estrategia)
creció en puntos absolutos, haciendo cada vez más difícil entrar dentro del
2% de riesgo al lote mínimo. El subconjunto de 12 no es solo chico, también
está sesgado hacia el tramo de precio ya superado - un motivo más para no
darle ningún peso a ese 1.09.

**Conclusión**: el concepto tiene una ventaja estadística real y robusta
(PF 1.89 sobre 55 señales, el número más alto y consistente de todo este
proyecto - muestra sólida, no la de 12). Lo que está bloqueado es la
*ejecución* con el capital actual, no la validez del hallazgo. **No se
activa todavía** en cuenta real (falta la mecánica de órdenes pendientes,
punto de abajo), y la fracción ejecutable debería crecer sola con el
capital, sin tocar código - se recalcula solo, igual que el resto del
sistema.

**Sin flag de producción** todavía: falta resolver la mecánica de
colocar/vigilar/cancelar las dos pendientes en `MT5Client` (no existe hoy,
el bot solo manda mercado en vela cerrada - decisión de arquitectura del
14/09) antes de poder activar esto en vivo, aunque el concepto ya esté
validado estadísticamente. Si en el futuro se retoma: (a) construir esa
gestión de órdenes pendientes en `MT5Client`, (b) revalidar con datos más
recientes antes de ir a producción, (c) empezar en `DRY_RUN=true` como con
cualquier despliegue nuevo a cuenta real.

## Filtro de tendencia 4H para Oro (28/09/2026) — RECHAZADO (las 3 variantes)

El usuario pidió evaluar si descartar señales de 1H de la Metodología v2
que van en contra de la tendencia mayor de 4H mejora el backtest de Oro,
probando 3 formas de definirla: (a) precio vs SMA50 en 4H, (b) RSI(14) 4H
vs 50, (c) estructura de máximos/mínimos fractales en las últimas 20 velas
4H. Mismo período de 7 meses de referencia, RSI 35/65 vigente.

Implementado en `src/trend_filter.py` (`resample_to_4h`, `trend_by_sma`,
`trend_by_rsi`, `trend_by_structure`, `map_trend_to_h1` - sin lookahead, el
valor de una vela 4H solo está disponible desde el momento en que esa vela
ya cerró - y `TrendFilteredStrategy`, que envuelve
`StructuralPullbackStrategy` sin tocarla, descartando a HOLD cualquier
señal en contra de la tendencia vigente; una tendencia neutral no bloquea
nada). 11 tests en `tests/test_trend_filter.py`.
`scripts/backtest_trend_filter.py` (modo realista, con filtro de capital)
y `scripts/backtest_trend_filter_exploratory.py` (lote fijo, aísla la
calidad de señal del problema de capital) corren las 3 variantes contra el
benchmark.

**Vista realista** (capital real $715.24, filtro de capital sección 3.2
activo):

| Variante | Señales generadas | Trades ejecutables |
|---|---|---|
| Sin filtro (benchmark) | 77 | 2 |
| SMA50 4H | 18 | **1** |
| RSI 4H | 10 | **1** |
| Estructura 4H | 58 | **1** |

El filtro de capital ya deja solo 2 trades ejecutables sin ningún filtro
de tendencia - cualquier filtro adicional solo puede mantener o reducir
esa muestra, nunca aumentarla. Con n=1 en las 3 variantes es
matemáticamente imposible aplicar el criterio de aprobación (PF>1.5 +
consistencia entre mitades, que necesita al menos 2 trades para partir en
dos) - no se puede validar ni rechazar por falta de muestra.

**Vista exploratoria** (lote fijo 1.0, sin filtro de capital - aísla la
calidad de la señal en sí):

| Variante | Trades | Win rate | PF total | PF 1ra mitad | **PF 2da mitad** |
|---|---|---|---|---|---|
| Sin filtro (benchmark) | 42 | 33.3% | 1.31 | 1.99 | **0.59** |
| SMA50 4H | 14 | 50.0% | 2.44 | 8.88 | **0.30** |
| RSI 4H | 9 | 55.6% | 2.90 | 7.99 | **0.78** |
| Estructura 4H | 34 | 38.2% | 1.81 | 3.25 | **0.69** |

Acá sí hay muestra suficiente para concluir, y la conclusión es negativa
por un motivo más contundente que la falta de datos: **las 4 variantes
(incluido el benchmark sin filtro) tienen la segunda mitad del período
perdedora** (PF entre 0.30 y 0.78). Los PF totales de SMA50 (2.44) y RSI
(2.90) parecen muy buenos, pero están inflados por una racha fuerte en la
primera mitad que no se repite en la segunda - el patrón clásico de
inconsistencia temporal que el criterio de "split de mitades" del propio
usuario está diseñado para detectar. Ninguna de las 3 variantes mejora esa
inconsistencia respecto al benchmark sin filtro; SMA50 y estructura, de
hecho, la empeoran (2da mitad más perdedora que el benchmark).

**Decisión: NO se activa ninguna de las 3 variantes.** Falla en las dos
vistas por motivos distintos: en la realista, no hay muestra suficiente
para decidir (n=1, cuello de botella de capital); en la exploratoria, sí
hay muestra, y falla la consistencia entre mitades en las 4 configuraciones
probadas (incluido el propio benchmark actual). Esto último es un hallazgo
más general que excede al filtro de tendencia: la calidad de señal de Oro
en este período completo, con RSI 35/65, ya es inconsistente entre mitades
incluso sin ningún filtro nuevo (PF 1.99 vs 0.59) - algo que no se había
medido explícitamente antes en modo exploratorio con el umbral vigente
(los backtests anteriores de Oro con RSI 35/65 solo tenían 2 trades reales,
sin muestra para split de mitades). Sin flag de producción - no hace falta
código nuevo para reconsiderarlo, `TrendFilteredStrategy` ya es reusable
tal cual con la clase existente. No revisitar sin antes entender por qué
la señal de Oro en sí es inconsistente entre mitades del período, algo más
profundo que el filtro de tendencia puntual.

## Techo de riesgo 3% para Oro (28/09/2026) — RECHAZADO

El usuario pidió recalcular qué señales de Oro se hubieran podido ejecutar
(lote mínimo 0.01) si el techo de riesgo objetivo subiera de 2% a 3% del
capital, manteniendo todo lo demás igual (mismo período de 7 meses, mismo
capital real $715.24) - reportando trades adicionales desbloqueados,
PF/WR/drawdown, y la peor racha de pérdidas consecutivas en dólares.

Se agregó `BacktestResult.worst_losing_streak` a `src/backtester.py` (racha
de pérdidas consecutivas con mayor pérdida acumulada en dólares, no
necesariamente la de más operaciones - 4 tests nuevos en
`tests/test_worst_losing_streak.py`) y `scripts/backtest_risk_ceiling.py`
para la comparación.

**Resultado**:

| | Riesgo 2% (baseline) | Riesgo 3% |
|---|---|---|
| Trades | 2 | 8 (+6 desbloqueadas) |
| Win rate | 50.0% | **12.5%** |
| Profit factor | 2.36 | **0.20** |
| Drawdown | 1.7% | **19.2%** |
| Peor racha de pérdidas | 1 operación, -$11.87 | **7 operaciones seguidas, -$137.56** |

Split de mitades sobre las 8 (pedido, aunque la muestra ya es chica): 1ra
mitad (4 trades) PF 0.00 (perdedora total), 2da mitad (4 trades) PF 0.46 -
mala en las dos, sin ambigüedad. Con n=8 la muestra es chica, pero 7 de 8
operaciones perdedoras es un resultado demasiado lopsided para necesitar
más datos - las 6 señales adicionales que destraba el techo más alto (las
de SL más ancho, que antes quedaban bloqueadas al lote mínimo) resultan
ser, en esta ventana, justamente las de peor calidad.

**Decisión: NO se activa.** Subir el techo de riesgo no mejora nada, y
en este backtest empeora todo a la vez - drawdown, profit factor y racha
de pérdidas. Sin flag de producción - no hace falta código nuevo (el
techo de riesgo ya es el parámetro `RISK_PER_TRADE_PCT` existente), así
que no hay nada que "activar", solo la recomendación de no subirlo.

## Diagnóstico de la inconsistencia entre mitades de Oro (28/09/2026)

El filtro de tendencia 4H (sección de arriba) reveló que la señal base de
Oro (sin ningún filtro nuevo, RSI 35/65) ya es inconsistente entre mitades
del período de referencia (PF 1.99 la primera, PF 0.59 la segunda). El
usuario pidió investigar la causa de raíz en vez de seguir probando
filtros puntuales - análisis directo sobre las 42 operaciones del backtest
exploratorio (lote fijo, `data/xauusd_h1_raw.csv`), sin escribir código
nuevo (no hace falta - es un análisis de datos, no una feature).

**Hipótesis 1: ¿cambio de régimen de volatilidad? SÍ, pero al revés de lo
esperable** - la volatilidad no subió en la segunda mitad, bajó:

| | 1ra mitad (14/02-29/05) | 2da mitad (29/05-10/09) |
|---|---|---|
| ATR(14) promedio | 16.27 puntos | **12.28 puntos (-25%)** |
| Efficiency Ratio (Kaufman) | 0.023 | **0.006** (4x más lateral) |
| Cambio de precio neto | -9.6% | -2.2% |

La segunda mitad es un régimen más lateral, comprimido y ruidoso en
relación a lo poco que se movió - no una fase más volátil que "rompió" el
sistema, como podría asumirse a priori.

**Hipótesis 2: ¿operaciones ganadoras concentradas en pocos meses? NO** -
es un quiebre de régimen sostenido de 4 meses consecutivos, no una racha
mala aislada:

| Mes | Trades | Ganadoras | PnL neto (lote fijo) |
|---|---|---|---|
| Feb-Abr (10 trades) | — | 6 | **+$62.217 (los 3 meses positivos)** |
| May (transición) | 7 | 2 | +$2.089 |
| Jun-Sep (25 trades) | — | 6 | **-$28.960 (los 4 meses negativos)** |

Las velas de mayor rango del período (posibles shocks) se concentran casi
todas entre el 3 y el 24 de marzo/2026, pero esas operaciones puntuales
solo aportaron $3.053 de los $52.229 netos de la primera mitad - el shock
de marzo NO es lo que explica la buena racha inicial, es más amplia y
sostenida que eso.

**El dato más revelador - motivo de salida por mitad:**

| | 1ra mitad | 2da mitad |
|---|---|---|
| Trades | 16 | 26 |
| Win rate | 43.8% | **26.9%** |
| Salidas por TP | 7 | **7 (igual)** |
| Salidas por SL | 9 | **19** |
| Ganancia media / Pérdida media | $14,138 / -$5,193 (ratio 2.7:1) | $7,373 / -$3,605 (ratio 2.0:1) |

La cantidad de reversiones genuinas que llegan a TP es **idéntica** en las
dos mitades (7 y 7) - el sistema encuentra la misma cantidad de setups
reales en ambos regímenes. La segunda mitad generó 10 operaciones
adicionales que fueron directo a SL, sin sumar ninguna ganadora más - el
régimen lateral no eliminó las señales buenas, generó señales falsas
adicionales que el régimen volátil de la primera mitad no producía.

**Hipótesis 3: ¿coincide con un evento macro/estructural conocido?**
No se pudo confirmar desde este entorno (sin acceso a un calendario macro
verificado en esta sesión) - el quiebre de régimen cae a fin de
mayo/principios de junio de 2026. El patrón de los datos (fase de caída
fuerte y volátil seguida de una fase lateral comprimida) es consistente
con una digestión/consolidación posterior a un shock grande, pero es una
lectura del patrón de precios, no una causa confirmada - si el usuario
identifica un evento real de esa fecha, se podría cruzar.

**Síntesis**: no es que "la señal de Oro sea buena, solo la bloquea el
capital" - la señal cambió de calidad real a mitad del período de
referencia, coincidiendo con el pasaje de un régimen volátil/direccional a
uno lateral/comprimido. El motor de la asimetría (ganancias grandes que
compensan pérdidas chicas) sigue funcionando igual en las dos mitades - lo
que se rompe es la tasa de señales falsas, que casi se duplica en el
régimen lateral sin sumar ganadoras nuevas.

**Sin implementar nada** - esto era diagnóstico, pedido explícitamente sin
activar nada. Sugerencia para una futura iteración (no evaluada todavía):
en vez de filtrar por dirección (lo que ya se probó y falló, ver "Filtro
de tendencia 4H"), explorar un filtro por **régimen de volatilidad** -
por ejemplo, exigir un piso de ATR antes de operar la reversión, dado que
la tasa de señales falsas parece estar ligada a la compresión de
volatilidad, no a la dirección del precio.

## Filtro de piso de volatilidad (ATR) para Oro (28/09/2026) — señal validada, bloqueado por conflicto directo con el filtro de capital

Hipótesis surgida del diagnóstico anterior (sección de arriba): filtrar por
**régimen de volatilidad** en vez de por dirección — descartar una señal de
reversión (RSI 35/65 + vela de rechazo) si el ATR(14) en 1H al momento de la
señal está por debajo de un piso. Implementado en `src/volatility_filter.py`
(`VolatilityFilteredStrategy`, envuelve `StructuralPullbackStrategy` sin
tocarla, mismo patrón que `TrendFilteredStrategy`) - 5 tests en
`tests/test_volatility_filter.py`. `scripts/backtest_volatility_filter.py`
corre el benchmark vs varios pisos de ATR, vista realista y exploratoria,
con split de mitades - mismo período de 7 meses de referencia, capital real
$715.24.

**Piso inicial probado: 14.27** (ATR promedio del período completo). Después
se barrieron pisos más bajos (8, 10, 12) para buscar un punto intermedio.

**Vista exploratoria (lote fijo, aísla calidad de señal):**

| Piso ATR | Trades | Win rate | PF total | PF 1ra mitad | PF 2da mitad |
|---|---|---|---|---|---|
| Sin filtro (benchmark) | 42 | 33.3% | 1.31 | 1.99 | **0.59** |
| ≥8.00 | 41 | 31.7% | 1.25 | 1.89 | 0.58 |
| ≥10.00 | 38 | 34.2% | 1.32 | 1.95 | 0.63 |
| ≥12.00 | 33 | 42.4% | 1.86 | 2.42 | 1.21 |
| **≥14.27** | **24** | **50.0%** | **2.42** | **3.01** | **1.70** |

Los pisos bajos (8/10) prácticamente no cambian nada frente al benchmark -
la segunda mitad sigue perdedora. Recién a partir de ~12 empieza a mejorar
de forma clara, y **solo el piso 14.27 (el promedio del período completo)
cumple el criterio completo: profit factor, win rate Y consistencia entre
mitades mejoran a la vez, con las dos mitades por encima de 1.5** (3.01 y
1.70) - exactamente el resultado que predecía el diagnóstico: la señal de
Oro no está rota, lo que generaba la inconsistencia era una mayor tasa de
señales falsas en el régimen lateral/comprimido de la segunda mitad, y
filtrar por volatilidad las saca sin sacrificar las reversiones genuinas.

**Vista realista (capital real $715.24, filtro de capital sección 3.2
activo) - acá aparece el problema de fondo:**

| Piso ATR | Trades ejecutables | Resultado |
|---|---|---|
| Sin filtro (benchmark) | 2 | PF 2.36 |
| ≥8.00 | 1 | perdedor (-$11.87) |
| ≥10.00 | 1 | perdedor (-$11.87) |
| ≥12.00 | 0 | — |
| ≥14.27 | 0 | — |

**Ningún piso de ATR mejora la vista realista - todos igualan o empeoran,
y el piso que sí mejora la calidad de señal (14.27) la lleva a cero
directamente.** La causa no es casualidad ni muestra chica: es un choque
estructural entre los dos filtros. El filtro de capital de la sección 3.2
solo deja pasar señales con SL técnico angosto al lote mínimo (baja
volatilidad, casi por definición) - es exactamente el tipo de señal que el
piso de ATR excluye. Pedirle a la vez "SL angosto" (capital) y "ATR alto"
(volatilidad) sobre la misma señal es casi una contradicción con este
capital: las señales de mejor calidad detectadas por el filtro de
volatilidad son sistemáticamente las que el filtro de capital ya venía
descartando por SL ancho.

**Decisión: NO se activa todavía.** Sin flag de producción - no hace falta
código nuevo para reconsiderarlo, `VolatilityFilteredStrategy` ya es
reusable tal cual. Queda como el segundo hallazgo de calidad de señal
genuino de este proyecto (junto con RSI 35/65 en BTC y el straddle semanal)
que no se puede ejecutar hoy - documentado para no tener que redescubrirlo.

### Diagnóstico de seguimiento (28/09/2026): ¿el choque con el filtro de capital es inevitable, o se resuelve con capital? — se resuelve con capital

El párrafo original de esta sección (arriba) especulaba que el bloqueo "no
se resuelve únicamente con que el capital crezca" porque el filtro de
capital privilegia SL angosto y el piso de ATR exige lo contrario - una
lectura que sonaba a contradicción estructural. El usuario pidió
confirmarlo antes de cerrar el tema: **extraer, de las señales crudas que
pasan cada piso de ATR, la distribución real del ancho de SL técnico**, sin
tocar código - análisis ad hoc (no comiteado, reproducible con las mismas
piezas de `src/`) sobre las 77 señales crudas de Oro del período de
referencia.

**Resultado: hay variabilidad real, no un acoplamiento matemático
perfecto** - correlación (Pearson) ATR vs ancho de SL = **0.72** (fuerte,
no 1.0). Pero en esta muestra puntual de 7 meses, ninguna señal con ATR≥12
tiene un SL lo bastante angosto para pasar el umbral actual:

| Subconjunto | n | SL más angosto observado | Umbral actual ($715.24, 2%) |
|---|---|---|---|
| ATR ≥ 12 | 59 | 18.04 puntos | $14.30 |
| ATR ≥ 14.27 | 42 | 19.17 puntos | $14.30 |
| ATR < 12 (contraste) | 18 | 6.99 puntos (2 de 18 sí pasan hoy) | — |

La brecha entre el SL más angosto de la banda ATR≥12 (18.04) y el umbral
actual (14.30) es de solo $3.74 - no es una distancia estructural enorme.
Traducido a capital necesario (2% de riesgo objetivo):

| Capital | Señales ATR≥14.27 ejecutables |
|---|---|
| $715 (actual) | 0/42 (0%) |
| ~$900-960 | empieza a entrar la primera |
| $1.300 | 5/42 (12%) |
| $2.000 | 11/42 (26%) |
| $2.500 | 22/42 (**52%**) |
| $3.000 | 30/42 (71%) |

**Corrección a la conclusión original de esta sección**: el bloqueo NO es
un choque estructural entre dos filtros que exigiría rediseñar el filtro
de capital - se resuelve con crecimiento de capital, igual que el resto de
las limitaciones de Oro en este proyecto (sección 3.2, straddle semanal).
La diferencia con esos otros casos es que acá ya queda cuantificado
cuánto capital hace falta: recién con ~$900-1.000 empieza a entrar la
primera señal filtrada por volatilidad, y con ~$2.000-2.500 (2.8x-3.5x el
capital actual) entraría una porción relevante (26%-52%) de la muestra de
7 meses. No se tocó ningún parámetro ni filtro - el hallazgo de calidad de
señal (piso 14.27) sigue sin flag de producción, pendiente de que el
capital llegue a ese rango antes de volver a evaluarlo con datos más
recientes.

## Metodología v2 "pura" para BTC (28/09/2026) — RECHAZADA

Surge del diagnóstico del 24/09/2026 sobre Oro ("Diferencia entre
operaciones manuales y detección del bot en Oro", más arriba): el bot en
producción exige dos requisitos que no surgen de la sección 4 del sistema
- (1) una vela de confirmación adicional después de la vela de rechazo, y
(2) un SL calculado sobre el mínimo/máximo de una ventana de 8 velas de
pullback, en vez del punto técnico más ajustado (extremo de la propia vela
de rechazo). La sospecha era que esto explica el silencio de BTC (2
semanas sin señales) - se pidió cuantificarlo formalmente en vez de
asumirlo, ya que en Oro no se había tocado código en ese momento.

Implementado en `src/strategies/pure_v2.py` (`PureV2Strategy`, hereda de
`StructuralPullbackStrategy` y solo sobreescribe `_analyze` - mismo RSI
35/65, mismo test geométrico de vela de rechazo, mismo nivel estructural,
mismo volumen y TP; cambia unicamente el timing de entrada -sin esperar
confirmación, actúa sobre la vela de rechazo misma- y el cálculo del SL
-extremo de esa única vela, no la ventana de 8-) - 4 tests en
`tests/test_pure_v2.py`, verificados numéricamente.
`scripts/backtest_pure_v2.py` corre ambas versiones sobre BTC, mismo
período de 7 meses de referencia, capital real $715.24.

**Vista realista (capital real, filtro de riesgo activo):**

| | Bot actual | v2 pura |
|---|---|---|
| Señales / Trades | 118 / 60 | 209 / **126** |
| Win rate | 46.7% | 31.7% |
| Profit factor | **1.71** | **0.91 (perdedora)** |
| Drawdown | 7.9% | **45.9%** |
| PF 1ra mitad | 1.40 | 0.95 |
| PF 2da mitad | 1.98 | 0.85 |

**Vista exploratoria (lote fijo, aísla calidad de señal):**

| | Bot actual | v2 pura |
|---|---|---|
| Trades | 45 | 127 |
| Win rate | 44.4% | 31.5% |
| Profit factor | 1.93 | **0.90** |
| Drawdown | 24.7% | **79.4%** |

Sacar la vela de confirmación y ajustar el SL a la vela de rechazo sola
**sí multiplica la frecuencia** (2-3x más señales/trades, confirmando esa
parte de la sospecha), pero **destruye la calidad**: profit factor por
debajo de 1.0 (sistema perdedor) en las dos vistas, consistente en las dos
mitades del período (pierde en ambas, no es una racha puntual), y
drawdown 4-6x mayor. Falla los tres criterios de aprobación (PF>1.5, sin
regresión, consistencia entre mitades) por un margen amplio, no un caso
límite.

**Lectura**: las dos "estrictezas" del bot, lejos de ser fricciones sin
sentido, sostienen el profit factor - la vela de confirmación filtra
patrones de rechazo que no continúan en la dirección esperada, y el SL más
ancho (ventana de 8 velas en vez de una sola) le da a la operación margen
contra la volatilidad normal antes de llegar a TP. Sin ellas, muchas
operaciones que habrían cerrado en TP quedan barridas por SL antes.

**Decisión: NO se implementa.** El silencio de BTC en el período reciente
(2 semanas sin señales, motivo original de la sospecha) **no se explica
por este criterio** - hay que buscar la causa en otro lado si se repite
(régimen de mercado sin setups válidos, algo similar al diagnóstico de
Oro). Sin flag de producción - no hace falta código nuevo para
reconsiderarlo, `PureV2Strategy` ya es reusable tal cual si en el futuro
se quiere probar una variante intermedia (por ejemplo, sacar solo uno de
los dos requisitos en vez de los dos a la vez).

## Metodología v2 en Oro 4H (28/09/2026) — muestra insuficiente, sin conclusión

Primer paso pedido por el usuario para evaluar sumar **swing trading al day
trading actual** (mixear ambos, no reemplazar). Mismo esqueleto ya validado
en producción (RSI(14) real cruzando 35/65 en vela cerrada, vela de rechazo
con el test geométrico estricto, nivel estructural, SL por estructura +
margen de ATR, TP al próximo nivel) - `StructuralPullbackStrategy` no se
toca, solo cambia `timeframe="H4"` y los datos de entrada.
`scripts/backtest_gold_4h.py` resamplea el mismo CSV H1 de referencia (7
meses) a velas 4H con `resample_to_4h` (`src/trend_filter.py`, ya usada
para el filtro de tendencia 4H) - sin descargar datos nuevos, 1.251 velas
4H resultantes.

**Resultado:**

| | Valor |
|---|---|
| Señales crudas | 27 |
| Trades (exploratorio, lote fijo) | **9** |
| Win rate | 44.4% |
| Profit factor | 1.11 |
| 1ra mitad (4 trades) | PF 0.32 |
| 2da mitad (5 trades) | PF 3.05 |
| Trades ejecutables (realista, capital $715.24) | **0** de 9 |

**No se puede aplicar el criterio de aprobación (ni aceptar ni rechazar)**:
n=9 es una muestra demasiado chica (menos de un cuarto de la usada para
validar RSI 35/65 en BTC), y el split de mitades (PF 0.32 vs 3.05, con 4 y
5 trades respectivamente) es ruido de muestra chica, no una señal de
consistencia real - mismo patrón ya visto con el subconjunto de 12 trades
ejecutables del straddle semanal (split 2.18/0.58). En vista realista, 0 de
9 pasan el filtro de capital de la sección 3.2 - mismo cuello de botella
estructural del resto de Oro, esperable porque el SL calculado sobre
velas de 4H (ventana de pullback + margen de ATR en esa escala) es
sistemáticamente más ancho en puntos que en 1H.

La causa de fondo es aritmética: los mismos 7 meses de referencia dan
~5.000 velas en 1H pero solo ~1.250 en 4H, y de esas solo 27 señales crudas
pasan los 4 filtros de la Metodología v2 - mismo problema de historial
corto que ya se vio con M30 (esa vez la conclusión se invirtió por completo
al conseguir más meses de datos), aplicado acá en la dirección de mayor
agregación en vez de mayor granularidad.

**Sin decisión de aceptar/rechazar todavía.** Sugerencia concreta para
retomar: extender el período de referencia (14-18 meses en vez de 7) para
juntar una muestra de al menos 25-30 trades ejecutables en vista realista
antes de evaluar PF y consistencia - Twelve Data ya mostró historial
limitado en el pasado (M30); si hace falta, se puede pedir un export más
largo directo de MT5 (mismo mecanismo que se usó para XAUUSDm en el
straddle semanal). Sin flag de producción - no hace falta código nuevo,
`StructuralPullbackStrategy(symbol=..., timeframe="H4")` ya es instanciable
tal cual, solo falta más historial.

## Diagnóstico de régimen de mercado en BTC (28/09/2026) — no es lo mismo que Oro

Motivado por 2 semanas sin ninguna operación ejecutada en BTC en la cuenta
real (mismo día que se descartó la Metodología v2 "pura" - ver más arriba -
que confirmó que el bot está bien calibrado, pero no explicaba el silencio
en sí). Mismo enfoque que el diagnóstico de Oro (sección de arriba): ATR,
Efficiency Ratio de Kaufman, frecuencia de toques de RSI extremo - más un
paso extra que en Oro no hizo falta: correr la lógica exacta de producción
candle por candle para localizar el filtro exacto que bloquea cada caso.

**Datos**: Twelve Data no llega a la fecha actual (el CSV de referencia de
7 meses termina el 09/09/2026) - se le pidió al usuario un export real de
MT5 de `BTCUSDm` H1 (01-28/09/2026, 668 velas), mismo mecanismo que se usó
para `XAGUSDm` y el straddle semanal de Oro.

**Resultado 1 - se descarta el patrón de Oro**: ATR, Efficiency Ratio y
frecuencia de toques de RSI extremo están todos en rango normal o por
encima del promedio histórico, no comprimidos:

| Métrica | Línea de base (7 meses) | Últimas 3 semanas |
|---|---|---|
| ATR(14) promedio | 420.43 | 422.04 (igual) |
| Efficiency Ratio semanal | 0.0848 | 0.063 / 0.116 / 0.138 / 0.084 / 0.155 |
| Toques de RSI 35/65 por semana | 34.97 | **41.7** (más, no menos) |

**Resultado 2 - la causa real, encontrada corriendo la logica exacta de
produccion** desde la ultima señal cruda (16/09 09:00) hasta hoy (298
velas x 2 direcciones = 596 chequeos):

| Filtro | Fallan | % de los que llegan |
|---|---|---|
| Vela de confirmación | 298 | 50% (normal) |
| Vela de rechazo (geometria) | 265 de 298 | 89% |
| RSI extremo + giro confirmado | **33 de 33** | **100%** |
| Volumen / Nivel | 0 | nunca se llego a chequear |

De los 33 casos con vela de rechazo + confirmación geometricamente validas,
ninguno coincidio con un RSI realmente extremo (29 nunca tocaron 35/65 en
la ventana, 4 tocaron pero no habian girado de vuelta para la vela de
confirmacion). **Es una desincronizacion puntual entre patron de vela y
momento de RSI extremo, no falta de ninguno de los dos por separado** -
ambos siguen ocurriendo a tasa normal, pero dejaron de coincidir en la
misma vela desde el 16/09.

**Resultado 3 - contexto historico**: el gap maximo entre señales crudas en
los 7 meses de referencia fue 10.9 dias (23/05-07/06). El silencio actual
(16/09-28/09, ~12.4 dias y contando) ya supera ese record - es la sequia
mas larga del periodo de referencia, no una racha tipica, aunque tampoco
astronomicamente fuera de rango dado lo sesgada a la derecha que ya era
la distribucion de gaps.

**Conclusión**: no es un bug del bot (se corrio su logica real, tal cual
esta en produccion, y se comporta exactamente como esta diseñada) ni un
cambio de regimen tipo Oro (volatilidad y frecuencia de RSI extremo son
normales o mas altas). Es ruido estadistico de una desincronizacion entre
dos condiciones que normalmente coinciden con cierta frecuencia - mas
inusual que el resto del historial reciente (nuevo record de silencio),
pero del mismo tipo de variacion que el sistema ya mostro antes (gaps de
7-11 dias ya habian aparecido). **No requiere ninguna accion de código** -
mismo espiritu que la decision 10 (el caso puntual de BTC post-Fed se
interpreto como ruido normal, no como falla estructural). Si el silencio
se extiende mucho mas alla de este record, ahi si ameritaria revisitarlo.

## Ventana de sincronización RSI-vela de rechazo en BTC (28/09/2026) — RECHAZADA (las 2 variantes)

Surge directo del diagnóstico de la sequía de BTC (sección de arriba): de
los 33 casos con vela de rechazo geométricamente válida desde el 16/09,
ninguno coincidió con un RSI genuinamente extremo en el mismo momento - 4
de ellos porque el RSI había tocado el extremo pero **todavía no había
girado de vuelta** (`rsi_confirmación` seguía del lado extremo) para el
momento de la vela de confirmación. Hipótesis: en vez de exigir el cruce
de vuelta ya confirmado, aceptar la vela de rechazo si aparece dentro de
`sync_window` velas después del último toque del extremo (nunca antes -
seguimos sin perseguir impulso).

Implementado en `src/strategies/sync_window.py` (`SyncWindowStrategy`,
hereda de `StructuralPullbackStrategy` y solo sobreescribe
`_rsi_extreme_and_turn` - todo lo demás, nivel, vela de rechazo geométrica,
vela de confirmación, volumen, SL/TP, queda igual) - 7 tests en
`tests/test_sync_window.py`, verificados numéricamente.
`scripts/backtest_sync_window.py` compara el bot actual vs las variantes
de 2 y 3 velas de ventana sobre BTC, mismo período de 7 meses, capital
real $715.24.

**Vista realista (capital real, filtro de riesgo activo):**

| | Señales | Trades | Win rate | Profit factor | Drawdown | PF 1ra/2da mitad |
|---|---|---|---|---|---|---|
| Bot actual (benchmark) | 118 | 60 | 46.7% | **1.71** | 7.9% | 1.40 / 1.98 |
| Ventana = 2 velas | 69 | 52 | 42.3% | **1.46** | 10.8% | 1.53 / 1.39 |
| Ventana = 3 velas | 81 | 57 | 43.9% | **1.52** | 11.0% | 1.74 / **1.37** |

**Vista exploratoria (lote fijo):**

| | Trades | Win rate | Profit factor | Drawdown |
|---|---|---|---|---|
| Bot actual (benchmark) | 45 | 44.4% | **1.93** | 24.7% |
| Ventana = 2 velas | 53 | 41.5% | **1.37** | **45.6%** |
| Ventana = 3 velas | 58 | 43.1% | **1.49** | **46.1%** |

**Se confirma exactamente el riesgo que se anticipó al plantear la
hipótesis**: ambas variantes suben la frecuencia de señales, pero el
profit factor cae en las dos vistas y el drawdown casi se duplica en la
vista exploratoria. Ventana=2 no llega ni al umbral de 1.5 en vista
realista. Ventana=3 técnicamente supera 1.5 (1.52) pero es una regresión
clara contra el benchmark (1.71→1.52) y **falla la consistencia entre
mitades** (1.74 en la primera, 1.37 en la segunda - la mitad más reciente
queda por debajo del umbral); en vista exploratoria confirma la
degradación (PF 1.49 vs 1.93 del benchmark, drawdown casi el doble).

**Decisión: NO se implementa ninguna de las dos.** Permitir que la vela de
rechazo aparezca mientras el RSI "está por girar" en vez de exigir que "ya
giró" agrega ruido, no señal genuina - el filtro de confirmación de giro
del RSI, igual que la vela de confirmación y el SL por ventana (ver
"Metodología v2 'pura' para BTC" más arriba), resulta ser otra exigencia
que sostiene el profit factor en vez de ser fricción innecesaria. La
sequía de 2 semanas se mantiene como variación estadística dentro de lo
que el sistema puede producir (ver diagnóstico de régimen de arriba), no
algo que convenga corregir con una regla permanente que empeora el perfil
general del bot. Sin flag de producción, `SyncWindowStrategy` queda
reusable tal cual si en el futuro se quiere probar otra variante puntual.

## Metodología de rango en Oro (28/09/2026) — muestra insuficiente, sin señal positiva

Hipótesis grande, pedida explícitamente por el usuario: sumar una segunda
estrategia que corra en PARALELO a la Metodología v2 (sin reemplazarla),
activándose solo en fase lateral/comprimida, para cubrir el tiempo donde
hoy Oro no opera nada porque el RSI no llega a un extremo real (35/65).
Diseño del usuario (punto de partida, con margen para ajustar detalles de
implementación):

1. Régimen: ADX(14) < 20 sostenido 8-10 velas consecutivas (elegido sobre
   la alternativa de ancho de Bollinger por integrarse mejor con el
   suavizado de Wilder ya usado en `rsi`/`atr`).
2. Entrada: RSI(14) toca 40 (no 35 - en rango angosto rara vez llega a
   extremos reales) + vela de rechazo con el mismo test geométrico
   estricto de siempre, cerca del piso del rango. Espejo con RSI 60 cerca
   del techo.
3. Salida: TP en el punto medio del rango (más conservador que el extremo
   opuesto, según pidió el usuario para el primer test), SL apenas afuera
   del piso/techo.
4. Verificar que no genere señales contradictorias con v2 en el mismo
   momento.

**Implementado**: `adx()` agregado a `src/indicators.py` (suavizado de
Wilder, mismo patrón que `rsi`/`atr` - 3 tests nuevos verificados con
series sintéticas de tendencia vs. rango).
`RangeReversionStrategy` (`src/strategies/range_reversion.py`) - el rango
se define con la MISMA ventana que confirma el régimen (sin agregar un
segundo parámetro de "ventana de rango"), la proximidad al piso/techo
reusa el mismo patrón que `StructuralPullbackStrategy._find_pullback_level`
(0.5x ATR). Decisión de diseño explícita y documentada en el código: a
diferencia de v2, NO exige una vela de confirmación separada (el diseño
del usuario solo menciona la vela de rechazo como gatillo) - marcado como
el punto mas discutible del diseño, dado que el backtest de "Metodología
v2 pura" del mismo día mostró que sacar la confirmación degrada BTC.
`scripts/backtest_range_reversion.py` corre el backtest completo mas el
chequeo de solapamiento con v2.

**Bug encontrado y corregido antes del resultado final**: la primera
corrida completa mostró 2 de 12 operaciones con RR de 0.01-0.02 - el
detector de régimen confirmaba un rango casi plano, dejando el TP (punto
medio) prácticamente pegado a la entrada, "ganancias" triviales que no
compensaban ningún riesgo real. Se agregó `min_range_atr_mult` (default
2.0: el rango completo tiene que medir al menos esa cantidad de ATRs) - 1
test nuevo, y se volvió a correr el backtest completo con el fix aplicado
antes de reportar nada como definitivo.

**Resultado final (con el fix aplicado):**

| | Valor |
|---|---|
| Señales crudas | 11 |
| Trades ejecutables (realista, $715.24) | **1** (perdedor, -$13.97) |
| Trades (exploratorio, lote fijo) | 10 |
| Win rate | 40.0% |
| Profit factor (exploratorio) | **0.95** (perdedora) |
| Drawdown | 45.2% |
| PF 1ra mitad (5 trades) | 1.25 |
| PF 2da mitad (5 trades) | **0.52** |

**Chequeo de solapamiento con v2 (punto 4 del pedido)**: 0 de 11 señales de
rango coincidieron con una señal cruda de v2 en la misma vela - el
detector de régimen separa bien los dos estados, sin contradicciones. Esa
parte del diseño funciona como se pidió.

**No cumple el criterio de aprobación, con advertencia fuerte de muestra
chica.** 10 trades exploratorio es bastante menos que el estándar del
proyecto (59 en BTC para RSI 35/65, 55 en el straddle semanal), y en
vista realista queda en n=1 - no alcanza para una conclusión estadística
firme. A diferencia de M30 (donde ampliar el historial invirtió la
conclusión), acá el cuello de botella no es la cantidad de datos
disponibles (mismos 7 meses de siempre) sino la combinatoria de 5
condiciones simultáneas (régimen sostenido + RSI en zona + vela de
rechazo + proximidad al borde + ancho mínimo de rango), que genera pocas
señales con estos parámetros puntuales. Dicho eso, la dirección es
consistentemente negativa: PF por debajo de 1.0 en la única vista con
algo de muestra, y el único trade ejecutable en cuenta real fue perdedor.

**Decisión original (revisada mismo día, ver subsección de abajo): NO se
activa.** La lectura inicial ("demasiado restrictivo para generar
muestra, no necesariamente malo") quedó corregida tras probar aflojar los
parámetros - ver más abajo.

### Intento de aflojar parámetros (28/09/2026) — empeora en los 3 ejes, se cierra el concepto

El usuario pidió aflojar los 3 filtros más restrictivos para ver si
generaban más señales sin perder calidad: (1) régimen más laxo (ADX<25 en
vez de <20, 6 velas en vez de 8), (2) banda de RSI más ancha (45/55 en vez
de 40/60), (3) proximidad al borde más laxa (20% del rango en vez de
0.5x ATR - para esto se agregó `level_proximity_pct_of_range` a
`RangeReversionStrategy`, 1 test nuevo). Probados de a uno primero
(triage rápido, solo conteo de señales crudas sin `RiskManager`, ~20s por
variante en vez de los ~80 min que tardaba antes recalcular el benchmark
de v2 en cada corrida - se optimizó `scripts/backtest_range_reversion.py`
para calcular v2 una sola vez).

**Triage (señales crudas)**: régimen laxo 11→29, RSI 45/55 11→27,
proximidad sola 11→11 (sin efecto, no era el cuello de botella). Con esto
se decidió correr el backtest completo para régimen laxo, RSI 45/55, y
los 3 combinados (proximidad sola no se corrió completa, no tenía sentido
sin efecto en el triage).

**Resultado completo:**

| Variante | Señales | Realista (trades/WR/PF) | Exploratorio (trades/WR/PF/DD) | Split 1ra/2da |
|---|---|---|---|---|
| Baseline | 11 | 1 / 0% / 0.00 | 10 / 40% / 0.95 / 45.2% | 1.25 / 0.52 |
| 1) Régimen laxo | 29 | 2 / 0% / 0.00 | 26 / 42.3% / **0.67** / **104.2%** | 1.41 / **0.20** |
| 2) RSI 45/55 | 27 | 2 / 0% / 0.00 | 20 / 40% / **0.68** / **84.5%** | 1.05 / 0.39 |
| 1+2+3 combinado | 58 | 4 / 0% / 0.00 | 47 / 48.9% / **0.66** / **138.0%** | 1.23 / 0.29 |

Solapamiento con v2: 0 en las 4 variantes, sin contradicciones en ninguna
- esa parte del diseño sigue funcionando bien en todos los casos.

**Aflojar cualquiera de los 3 ejes empeora, no mejora**: profit factor
exploratorio cae de 0.95 a 0.66-0.68 en las tres variantes (nunca sube),
drawdown se dispara de 45% a 84-138%, y la segunda mitad del período pasa
de ya mala (0.52) a catastrófica (0.20-0.39) en cada una. **En vista
realista, 0% de win rate en las 4 variantes combinadas (0 de 8 operaciones
reales)** - un patrón demasiado consistente entre variantes independientes
para atribuirlo solo a la muestra chica.

**Corrección de la conclusión original**: no es que el diseño fuera
"demasiado restrictivo pero potencialmente bueno" - aflojar en 3 ejes
independientes y ver que empeora en los tres indica que el combo
régimen+RSI 40/60+rechazo+punto medio no encuentra buenas oportunidades en
Oro incluso con más espacio para operar. Más señales, pero sistemáticamente
de peor calidad, no señales buenas diluidas por ruido.

**Decisión final: se cierra el concepto tal como está diseñado.** No
seguir ajustando régimen/RSI/proximidad - ya se probó en las 3 direcciones
y las 3 empeoran. Si se quiere retomar la idea de cubrir el tiempo sin
operar en Oro, el camino más prometedor sin probar todavía es TP en el
extremo opuesto del rango en vez del punto medio (la única variante del
diseño original que queda sin evaluar) - un cambio de diseño distinto, no
un aflojamiento de filtros. Sin flag de producción.

## Próximos pasos pendientes

1. Juntar operaciones reales de la cuenta real con la Metodología v2 (RSI
   35/65 desde el 20/09/2026) y compararlas contra el número de referencia
   vigente (PF 1.88, WR 47.5% en BTC realista; Oro sin operaciones
   esperables por ahora - ver "Backtest del umbral de RSI relajado"). Al
   17/09/2026 hay 2 operaciones reales cerradas, ambas BTC en positivo:
   +$9.96 (15/09) y +$0.47 (16-17/09, cierre manual tras ~24hs de
   lateralización - el caso que motivó la sección 6.1). Esas dos
   operaciones se hicieron con el RSI 30/70 anterior, así que no son
   comparables 1:1 contra el número de referencia nuevo.
2. Filtro de tendencia de 4H sigue pendiente de una siguiente iteración -
   no empezar sin que el usuario lo pida. Notificaciones (mail, no
   Telegram - el usuario no lo usa) están en curso, ver punto 7.
3. El sistema de reversión por RSI extremo en 1H como estrategia SEPARADA
   ya no es un pendiente: quedó absorbido dentro de la Metodología v2.
4. ETH (`ETHUSDm`) queda evaluado y con el código listo pero apagado
   (`ENABLE_ETH=false`) - ver "Evaluación de ETH como tercer símbolo" más
   abajo. No revisitar activarlo sin (a) verificar las specs reales de
   contrato de `ETHUSDm` en el Market Watch de la cuenta y (b) volver a
   correr el backtest con esas specs confirmadas.
5. La estrategia de ruptura de consolidación (`BreakoutStrategy`) queda
   evaluada y rechazada (`ENABLE_BREAKOUT_STRATEGY=false`) - ver
   "Estrategia de ruptura de consolidación" más abajo. No revisitar sin
   repensar el criterio de entrada primero (el problema es la calidad de
   la señal, no el bucket de capital ni el esquema de SL/TP).
6. El stop a breakeven (50%/70% de distancia al TP) queda evaluado y
   rechazado - ver "Backtest del stop a breakeven" más abajo. Baja el
   profit factor de BTC frente al baseline en las dos variantes probadas
   (aunque sube el win rate); no tiene flag de producción porque además
   requeriría agregar modificación de posición real a `MT5Client`. Si se
   revisita, probar primero con otros umbrales/buffer sobre
   `run_backtest(enable_breakeven_stop=...)` antes de construir la parte
   de MT5.
7. Timeframe M30 para BTC queda evaluado y rechazado (7 meses completos:
   PF 1.04, DD 42.3%, pierde en la primera mitad del período) - ver
   "Timeframe M30 para BTC" más arriba.
8. Notificaciones por mail: implementadas y **activadas y validadas en
   producción el 24/09/2026** - ver "Notificaciones por mail" más arriba.
   Ya no es un pendiente; queda como referencia el uso de
   `scripts/test_email.py` si en el futuro hace falta volver a validar el
   envío (por ejemplo, si el usuario regenera la Contraseña de aplicación
   de Gmail).
9. Plata (`XAGUSDm`) evaluada como tercer instrumento y **rechazada**
   (24/09/2026) - ver "Evaluación de Plata (XAG/USD) como tercer
   instrumento" más arriba. PF 0.24 / WR 16.0% incluso sin el filtro de
   capital (falla la calidad de señal, no solo el sizing), y además el
   filtro de capital de la sección 3.2 bloquea el 100% de las señales
   (0 de 25) igual que a Oro. Sin flag de producción - no hace falta
   código nuevo para reconsiderarlo, ya es instanciable con la clase
   existente. No revisitar sin repensar el criterio de entrada para este
   instrumento en particular (el problema es la señal, no el capital).
10. Diferencia entre operaciones manuales y detección del bot en Oro
    (24/09/2026) - ya respondida, no es un pendiente accionable, queda
    como referencia. Ver "Diferencia entre operaciones manuales y
    detección del bot en Oro" más arriba: timing de confirmación y
    estrictez de la vela de rechazo explican las 2 operaciones puntuales
    analizadas, más la diferencia de fondo de tipo de orden (Buy Limit
    manual vs. mercado en vela cerrada del bot). No se cambió ningún
    parámetro de la estrategia.
11. Straddle de reapertura semanal (Oro) - **validado estadísticamente el
    27/09/2026** (PF 1.89 en R, TP 1x, consistente en mitades y ante
    distintos parámetros - el resultado más fuerte de todo este proyecto),
    pero **bloqueado en la práctica por el filtro de capital** (78% de las
    señales no ejecutables con el capital actual, igual que el resto de
    Oro) y sin flag de producción (falta construir gestión de órdenes
    pendientes en `MT5Client`, que hoy no existe). Ver "Evaluación del
    straddle de reapertura semanal" más arriba para el detalle completo,
    incluida la verificación de spread en la reapertura y la aclaración
    sobre OCO (no depende de Exness, es mecánica de `MT5Client`). No
    revisitar activarlo sin (a) que el capital crezca lo suficiente para
    que más señales entren en el 2% de riesgo, y (b) construir esa gestión
    de órdenes pendientes.
12. Filtro de tendencia 4H para Oro (SMA50/RSI/estructura) - **rechazado
    (28/09/2026)**, las 3 variantes. Ver "Filtro de tendencia 4H para Oro"
    más arriba. En modo realista la muestra es insuficiente (n=1 en las 3,
    mismo cuello de botella de capital); en modo exploratorio (sí hay
    muestra) las 4 configuraciones - incluido el benchmark sin filtro -
    tienen la segunda mitad del período perdedora, ninguna mejora esa
    inconsistencia. Hallazgo más amplio: la señal de Oro con RSI 35/65 ya
    es inconsistente entre mitades del período de referencia, más allá de
    este filtro puntual - no revisitar sin primero entender esa
    inconsistencia de fondo.
13. Techo de riesgo 3% para Oro - **rechazado (28/09/2026)**. Ver "Techo
    de riesgo 3% para Oro" más arriba. Las 6 señales adicionales que
    destraba (SL más ancho) son las de peor calidad en la ventana: PF 0.20,
    7 de 8 operaciones perdedoras, peor racha -$137.56. No hay nada que
    "activar" - `RISK_PER_TRADE_PCT` sigue en 2.0, es la recomendación de
    no subirlo, no una feature pendiente.
14. Diagnóstico de la inconsistencia entre mitades de Oro (28/09/2026) -
    ya respondido, no es un pendiente accionable, queda como referencia.
    Ver "Diagnóstico de la inconsistencia entre mitades de Oro" más
    arriba: la 2da mitad del período no fue más volátil, fue más lateral y
    comprimida (ATR -25%, Efficiency Ratio 4x menor) - la cantidad de
    reversiones genuinas (salidas por TP) es idéntica en las dos mitades
    (7 y 7), pero el régimen lateral generó 10 salidas por SL adicionales
    sin sumar ninguna ganadora más. Sugerencia sin evaluar todavía para una
    futura iteración: filtro por régimen de volatilidad (piso de ATR) en
    vez de por dirección (lo que ya se probó y falló).
15. Filtro de piso de volatilidad (ATR) para Oro - **señal validada,
    bloqueado por capital, cuantificado (28/09/2026)**. Ver "Filtro de piso
    de volatilidad (ATR) para Oro" más arriba. En vista exploratoria
    confirma el diagnóstico: piso 14.27 mejora PF (1.31→2.42), win rate
    (33.3%→50.0%) y arregla la inconsistencia entre mitades (0.59→1.70 en
    la 2da mitad) a la vez. En vista realista da 0 trades ejecutables hoy -
    pero el diagnóstico de seguimiento (mismo día) confirmó que **sí se
    resuelve con crecimiento de capital** (no es un choque estructural
    irresoluble entre filtros, como se había especulado inicialmente):
    correlación ATR-vs-SL 0.72 (variabilidad real, no acoplamiento
    perfecto), y con ~$900-1.000 ya entraría la primera señal filtrada,
    ~$2.000-2.500 destrabaría 26%-52% de la muestra de 7 meses. Sin flag de
    producción - no hace falta código nuevo para reconsiderarlo, solo que
    el capital llegue a ese rango y volver a correr el backtest con datos
    más recientes.
16. Metodología v2 "pura" para BTC (sin vela de confirmación extra, SL en
    la vela de rechazo sola) - **rechazada (28/09/2026)**. Ver "Metodología
    v2 'pura' para BTC" más arriba. Multiplica la frecuencia (2-3x más
    trades) pero el profit factor cae por debajo de 1.0 en las dos vistas
    (realista y exploratoria) y en las dos mitades del período, con
    drawdown 4-6x mayor. La vela de confirmación y el SL por ventana de 8
    velas no son fricciones sin sentido - sostienen el profit factor. El
    silencio de BTC que motivó la pregunta no se explica por este criterio
    de entrada. Sin flag de producción, `PureV2Strategy`
    (`src/strategies/pure_v2.py`) queda reusable tal cual si se quiere
    probar una variante intermedia (sacar solo uno de los dos requisitos).
17. Metodología v2 en Oro 4H (primer paso hacia swing trading) - **muestra
    insuficiente, PAUSADO hasta que crezca el capital (28/09/2026)**. Ver
    "Metodología v2 en Oro 4H" más arriba. Solo 9 trades en vista
    exploratoria y **0 ejecutables en vista realista** sobre los mismos 7
    meses de referencia (que en 4H dan ~1.250 velas en vez de ~5.000).
    Split de mitades (PF 0.32 vs 3.05) es ruido de muestra chica, no
    señal - técnicamente se podría conseguir más historial (14-18 meses)
    para juntar una muestra mayor y volver a evaluar la calidad de la
    señal en sí, pero el usuario decidió explícitamente pausarlo: aunque
    la señal resultara buena, la ejecución real seguiría bloqueada por el
    mismo filtro de capital de la sección 3.2 que ya bloquea el resto de
    Oro (SL en 4H sistemáticamente más ancho que en 1H) - no tiene sentido
    invertir en conseguir más datos históricos todavía si el resultado no
    se podría operar en cuenta real de todas formas. Retomar cuando el
    capital crezca lo suficiente como para que el filtro de capital deje
    de ser el cuello de botella dominante en Oro en general (ver también
    el techo de riesgo y el filtro de volatilidad, mismo patrón) - recién
    ahí conseguir más historial en 4H y revalidar. Sin flag de producción,
    no hace falta código nuevo.
18. Diagnóstico de régimen de mercado en BTC (28/09/2026) - ya respondido,
    no es un pendiente accionable, queda como referencia. Ver "Diagnóstico
    de régimen de mercado en BTC" más arriba: a diferencia de Oro, ATR y
    frecuencia de toques de RSI extremo están en rango normal o por encima
    del promedio - no hay compresión de volatilidad. La causa real es una
    desincronización puntual entre la geometría de la vela de rechazo y el
    momento del RSI extremo (100% de los candidatos que llegan a ese
    filtro fallan ahí desde el 16/09) - ruido estadístico, no un bug ni un
    cambio de régimen. El silencio actual (~12.4 días) ya es récord sobre
    el histórico de 7 meses (máximo previo: 10.9 días), pero del mismo tipo
    de variación ya vista antes. No requiere ninguna acción de código.
19. Ventana de sincronización RSI-vela de rechazo en BTC - **rechazada,
    las 2 variantes (28/09/2026)**. Ver "Ventana de sincronización
    RSI-vela de rechazo en BTC" más arriba. Aceptar la vela de rechazo
    dentro de 2 o 3 velas después del toque de RSI extremo (en vez de
    exigir que el RSI ya haya girado) sube la frecuencia pero baja el
    profit factor en las dos vistas y casi duplica el drawdown en la vista
    exploratoria (45-46% vs 24.7%). Ventana=3 técnicamente supera PF 1.5
    en vista realista pero es regresión contra el benchmark y falla
    consistencia entre mitades (1.74/1.37). El filtro de "giro ya
    confirmado" del RSI sostiene el profit factor, no es fricción sin
    sentido - misma conclusión que con la vela de confirmación y el SL por
    ventana en la Metodología v2 "pura". Sin flag de producción,
    `SyncWindowStrategy` (`src/strategies/sync_window.py`) queda reusable
    tal cual para otra variante puntual.
20. Metodología de rango en Oro (sistema paralelo a v2, activo en fase
    lateral) - **CERRADA, aflojar parámetros empeora en los 3 ejes
    probados (28/09/2026)**. Ver "Metodología de rango en Oro" más arriba,
    incluida la subsección "Intento de aflojar parámetros". Baseline: 10
    trades exploratorio PF 0.95, 1 en realista (perdedor). Se probó
    aflojar régimen (ADX<25/6v), banda de RSI (45/55) y proximidad (20%
    del rango), de a uno y combinados - los 3 ejes SUBEN la frecuencia
    (11→27-58 señales) pero BAJAN el profit factor exploratorio (0.95→
    0.66-0.68) y DISPARAN el drawdown (45%→84-138%); en vista realista, 0%
    de win rate en las 4 variantes combinadas (0 de 8 trades). No es un
    problema de muestra chica que se resuelva con más señales - el
    combo régimen+RSI+rechazo+punto medio no encuentra buenas
    oportunidades en Oro, y aflojarlo solo suma señales de peor calidad.
    Sin solapamiento/contradicción con v2 en ninguna variante (0 en las
    4). Sin flag de producción. Si se retoma la idea en el futuro: no
    seguir aflojando régimen/RSI/proximidad (ya probado, empeora) - la
    única variante de diseño sin evaluar es TP en el extremo opuesto del
    rango en vez del punto medio.

## Cómo correr cosas

Ver `README.md` (sección "Puesta en marcha") para los pasos completos de
instalación/arranque en la PC del usuario. Resumen rápido de comandos ya
usados con éxito en su máquina (Windows, PowerShell):

```
cd Primer-proyecto
.venv\Scripts\activate
python -m src.bot
```

Los tests (`pytest tests/ -v`, 74 tests) y los scripts de backtest
(`scripts/backtest_from_csv.py`, `scripts/list_signals.py`) corren en
cualquier entorno con las dependencias instaladas, no requieren MT5. Lo
mismo `scripts/summarize_bot_log.py` (24/09/2026) - resume `logs/bot.log`
(actividad por símbolo, arranques, posibles caídas) sin tener que leerlo a
mano, ver README ("Diagnosticar logs/bot.log").
