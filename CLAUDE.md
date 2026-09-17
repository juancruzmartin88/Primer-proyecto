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
   estructural + RSI extremo real (cruce de 30/70, no solo 50) + giro de
   RSI confirmado + vela de rechazo/confirmación + volumen (si los datos lo
   traen). Confirmada con las dos primeras operaciones reales que la
   aplicaron completa: BTC +$11.00 (11/09) y Oro +$134.07 (14/09), ambas TP.
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
  Drawdown máximo historico bajo (11.9% sobre $650), riesgo por operación
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

## Próximos pasos pendientes

1. Juntar operaciones reales de la cuenta real con la Metodología v2 y
   compararlas contra estos números de referencia (PF 1.36 BTC realista al
   14/09; PF 1.73 con la muestra ampliada del 17/09; Oro sin operaciones
   esperables por ahora). Al 17/09/2026 hay 2 operaciones reales cerradas,
   ambas BTC en positivo: +$9.96 (15/09) y +$0.47 (16-17/09, cierre manual
   tras ~24hs de lateralización - el caso que motivó la sección 6.1).
2. Filtro de tendencia de 4H y notificaciones (ej. Telegram) siguen
   pendientes de una siguiente iteración - no empezar sin que el usuario
   lo pida.
3. El sistema de reversión por RSI extremo en 1H como estrategia SEPARADA
   ya no es un pendiente: quedó absorbido dentro de la Metodología v2.

## Cómo correr cosas

Ver `README.md` (sección "Puesta en marcha") para los pasos completos de
instalación/arranque en la PC del usuario. Resumen rápido de comandos ya
usados con éxito en su máquina (Windows, PowerShell):

```
cd Primer-proyecto
.venv\Scripts\activate
python -m src.bot
```

Los tests (`pytest tests/ -v`, 44 tests) y los scripts de backtest
(`scripts/backtest_from_csv.py`, `scripts/list_signals.py`) corren en
cualquier entorno con las dependencias instaladas, no requieren MT5.
