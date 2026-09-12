# Contexto del proyecto (leer antes de tocar nada)

Bot de trading algorítmico para la cuenta demo de Exness del usuario,
desarrollado con Claude a lo largo de varias sesiones (empezó 09/09/2026,
en producción desde 10/09/2026). Este archivo existe para que una sesión
nueva de Claude Code tenga el contexto completo sin tener que releer todo
el historial de chat.

## Estado actual (10/09/2026, fin de la sesión de puesta en marcha)

**El bot está corriendo en vivo**, en la PC del usuario (Windows), conectado
a su cuenta demo de Exness:

- Cuenta: `198944861`, servidor `Exness-MT5Trial11`, tipo Standard, balance $400.
- Símbolo operado: **`BTCUSDm`** únicamente (nota el sufijo "m" - ver mas abajo).
- `DRY_RUN=false` → el bot manda órdenes reales a la cuenta demo, sin pedir
  confirmación cada vez. Es autónomo.
- Riesgo configurado: `RISK_PER_TRADE_PCT=1.5`, `MAX_DAILY_LOSS_PCT=3.0`,
  `MAX_OPEN_POSITIONS=1`.

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

1. **Estrategia**: `StructuralPullbackStrategy` (`src/strategies/structural_pullback.py`),
   traduce la sección 10 del documento original del usuario (sistema
   "Mediano/Largo" con pullback a nivel estructural). El sistema de
   reversión por RSI extremo en 1H ("Corto plazo") **no está implementado**.
2. **XAUUSD queda pausado** para el bot automático: con $400 de capital, el
   lote mínimo (0.01) fuerza ~4-7% de riesgo real por operación en vez del
   1.5% objetivo (verificado con backtest real). Hace falta ~$1500+ de
   capital para que XAUUSD tenga sentido automatizado. El usuario puede
   seguir operando Oro a mano; el bot no lo toca.
3. **Sufijo "m" en los símbolos**: la cuenta Standard del usuario nombra los
   instrumentos como `XAUUSDm`, `BTCUSDm` en vez de `XAUUSD`/`BTCUSD` a
   secas (verificado en Market Watch de MT5). `src/bot.py` tiene las
   constantes `XAUUSD_SYMBOL`/`BTCUSD_SYMBOL` para esto, y
   `config/levels.json` usa esas mismas claves con sufijo. Si el usuario
   cambia de cuenta/tipo en el futuro, hay que re-verificar el sufijo real
   en Market Watch antes de asumir que sigue siendo "m".
4. **Dos umbrales de la estrategia se relajaron (10/09/2026)** para subir la
   frecuencia de señales, que con los umbrales originales daba ~1 señal
   cada 12 días por instrumento:
   - Se sacó el requisito de que la vela de confirmación cierre más allá
     del extremo de la vela de rechazo (no estaba en el texto original del
     sistema, era un agregado propio y redundante con el cruce de RSI).
   - `rejection_wick_ratio` bajó de 2.0x a 1.5x (geometría de martillo/
     estrella fugaz menos estricta).
   - Validado con backtest de 7 meses: XAUUSD pasó de PF 2.10→2.04 (casi
     sin cambio, drawdown mejoró), BTCUSD de PF 1.51→1.39 (baja real pero
     dentro del ruido esperable con ~35-43 operaciones de muestra). Se
     decidió mantener los umbrales relajados porque la ganancia en
     frecuencia (necesaria para juntar una muestra estadística real) pesa
     más que esa caída de PF, que no es concluyente con esta muestra.
5. **Niveles estructurales** (`config/levels.json`): cargados a mano por el
   usuario (alertas de TradingView + niveles mencionados en su registro de
   operaciones), con fallback automático a fractales si un símbolo no tiene
   niveles cargados. Hay que mantenerlos actualizados a medida que cambian
   los niveles relevantes en el gráfico real.
6. **Gestión de riesgo real ya validada contra el historial real del
   usuario** (16 operaciones manuales, 30/08-09/09/2026): el `RiskManager`
   actual (position sizing automático + traba de SL/TP obligatorios)
   elimina por diseño los dos peores incidentes de ese historial (un error
   de cálculo manual que expuso 106% del capital en una operación, y una
   orden enviada sin SL/TP activo).

## Próximos pasos pendientes

1. Juntar operaciones reales de esta etapa (demo, `DRY_RUN=false`) y
   comparar el profit factor real contra el del backtest (2.04 XAUUSD /
   1.39 BTCUSD). El usuario sigue completando su planilla de registro
   manual (fecha, motivo, resultado, lección) en paralelo.
2. Si el profit factor real se sostiene y se completa la racha de 5-8
   operaciones sin error de proceso (criterio propio del usuario, sección 9
   de su documento original), evaluar el pase de BTC/USD a cuenta real.
3. XAUUSD se retoma cuando el capital llegue a la banda de ~$1500+.
4. Pendiente de una siguiente iteración (no empezar sin que el usuario lo
   pida): sistema de reversión por RSI extremo en 1H, filtro de tendencia
   de 4H, notificaciones (ej. Telegram) para no depender de mirar la
   ventana de PowerShell.

## Cómo correr cosas

Ver `README.md` (sección "Puesta en marcha en demo") para los pasos
completos de instalación/arranque en la PC del usuario. Resumen rápido de
comandos ya usados con éxito en su máquina (Windows, PowerShell):

```
cd Primer-proyecto
.venv\Scripts\activate
python -m src.bot
```

Los tests (`pytest tests/ -v`, 35 tests) y los scripts de backtest
(`scripts/backtest_from_csv.py`, `scripts/list_signals.py`) corren en
cualquier entorno con las dependencias instaladas, no requieren MT5.
