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
