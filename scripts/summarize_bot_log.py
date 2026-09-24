"""Resume logs/bot.log: actividad por simbolo, arranques y posibles caidas.

Pensado para responder rapido "¿el bot hizo algo con BTC/Oro en tal
periodo?" sin tener que leer miles de lineas a mano - el bot solo escribe
una linea cuando pasa algo (señal, bloqueo, error, orden) - ver
`src/bot.py::iterate`. Que un simbolo no tenga NINGUNA linea en un tramo no
es un sintoma de falla: significa que el bot lo revisó en cada vuelta del
loop (cada `POLL_INTERVAL_SECONDS`, 30s por defecto) y no encontró señal.

Uso:
    python -m scripts.summarize_bot_log logs/bot.log
    python -m scripts.summarize_bot_log logs/bot.log --gap-minutes 5
"""
from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

_LINE_RE = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+ \| (?P<level>\w+)\s*\| "
    r"(?P<source>[^-]+) - (?P<message>.*)$"
)
_SYMBOL_RE = re.compile(r"\b([A-Z]{3,6}USDm)\b")

_STARTUP_MARK = "Arrancando bot"
_CONNECTED_MARK = "Conectado a MT5"
_ERROR_MARK = "Error inesperado"
_ORDER_REJECTED_MARK = "Orden rechazada"
_ORDER_EXECUTED_MARK = "Orden ejecutada"
_DRY_RUN_MARK = "[DRY_RUN]"
_TIME_LIMIT_CLOSE_MARK = "cerrando posicion #"
# Avisos que el bot escribe UNA VEZ al arrancar (mencionan el simbolo en el
# texto, pero no son actividad de trading - se excluyen de "señales" por
# simbolo para no confundirlos con algo que realmente paso en esa vuelta
# del loop).
_BOOT_INFO_MARKS = (
    _STARTUP_MARK,
    "descarta automaticamente cualquier señal",  # recordatorio de la seccion 3.2 (Oro)
    "bucket de capital separado",  # recordatorio de BreakoutStrategy, si esta activa
)


def _parse_line(line: str) -> dict | None:
    match = _LINE_RE.match(line)
    if not match:
        return None
    return {
        "time": datetime.strptime(match.group("time"), "%Y-%m-%d %H:%M:%S"),
        "level": match.group("level"),
        "source": match.group("source").strip(),
        "message": match.group("message"),
    }


def summarize(log_path: str, *, gap_minutes: float = 5.0) -> None:
    with open(log_path, encoding="utf-8") as f:
        raw_lines = f.readlines()

    entries = [_parse_line(line) for line in raw_lines]
    entries = [e for e in entries if e is not None]
    if not entries:
        print(f"No se pudo parsear ninguna linea de {log_path} - ¿formato distinto al esperado?")
        return

    start = entries[0]["time"]
    end = entries[-1]["time"]
    print(f"Log: {log_path}")
    print(f"Rango cubierto: {start} -> {end} (hora del sistema del bot)")
    print(f"Total de lineas parseadas: {len(entries)}\n")

    startups = [e for e in entries if _STARTUP_MARK in e["message"]]
    print(f"Arranques del bot detectados: {len(startups)}")
    for e in startups:
        print(f"  {e['time']}  {e['message']}")
    print()

    by_symbol: dict[str, list[dict]] = defaultdict(list)
    other: list[dict] = []
    for e in entries:
        symbols = set(_SYMBOL_RE.findall(e["message"]))
        if symbols:
            for symbol in symbols:
                by_symbol[symbol].append(e)
        else:
            other.append(e)

    known_symbols = ["BTCUSDm", "XAUUSDm", "ETHUSDm"]
    all_symbols = sorted(set(known_symbols) | set(by_symbol.keys()))

    for symbol in all_symbols:
        symbol_entries = by_symbol.get(symbol, [])
        print(f"=== {symbol} ===")

        reasons = Counter()
        signals = []
        orders = []
        errors = []
        boot_info = []
        reasons_entries = []
        for e in symbol_entries:
            msg = e["message"]
            if any(mark in msg for mark in _BOOT_INFO_MARKS):
                boot_info.append(e)
            elif _ERROR_MARK in msg:
                errors.append(e)
            elif _ORDER_EXECUTED_MARK in msg or _DRY_RUN_MARK in msg:
                orders.append(e)
            elif _ORDER_REJECTED_MARK in msg:
                errors.append(e)
            elif "bloqueada por gestion de riesgo" in msg or "bloqueada" in msg:
                # Agrupa por el motivo (el texto despues del ultimo ": ").
                reason = msg.split(":", 1)[-1].strip() if ":" in msg else msg
                reasons[reason] += 1
                reasons_entries.append(e)
            elif _TIME_LIMIT_CLOSE_MARK in msg:
                signals.append(e)
            else:
                signals.append(e)

        real_activity = orders or signals or errors or reasons
        if not real_activity:
            note = " (aparte del aviso de arranque)" if boot_info else ""
            print(f"  Sin ninguna señal, orden ni bloqueo en el log{note} - normal si el bot")
            print("  corrio y nunca se cumplieron las 4 condiciones de entrada en ese")
            print("  periodo, no es evidencia de falla por si solo (el bot solo escribe")
            print("  una linea cuando pasa algo, no en cada vuelta que no encuentra nada).")
            print()
            continue

        real_lines = sorted(orders + signals + errors + reasons_entries, key=lambda e: e["time"])
        print(f"  Lineas totales: {len(symbol_entries)} (+ {len(boot_info)} avisos de arranque, excluidos abajo)")
        print(f"  Primera actividad real: {real_lines[0]['time']}  Ultima: {real_lines[-1]['time']}")
        if orders:
            print(f"  Ordenes (reales o [DRY_RUN]): {len(orders)}")
            for e in orders:
                print(f"    {e['time']}  {e['message'][:160]}")
        if signals:
            print(f"  Otras lineas relevantes (señales, cierres, etc.): {len(signals)}")
            for e in signals[:20]:
                print(f"    {e['time']}  {e['message'][:160]}")
            if len(signals) > 20:
                print(f"    ... y {len(signals) - 20} mas")
        if errors:
            print(f"  ERRORES/RECHAZOS: {len(errors)}")
            for e in errors:
                print(f"    {e['time']}  {e['message'][:200]}")
        if reasons:
            print("  Bloqueos por gestion de riesgo, agrupados por motivo:")
            for reason, count in reasons.most_common():
                matching = [e for e in symbol_entries if reason in e["message"]]
                print(
                    f"    x{count:<5} {reason}  "
                    f"(de {matching[0]['time']} a {matching[-1]['time']})"
                )
        print()

    if other:
        print(f"=== Lineas sin simbolo identificado ({len(other)}) ===")
        for e in other[:15]:
            print(f"  {e['time']} | {e['level']} | {e['message'][:160]}")
        if len(other) > 15:
            print(f"  ... y {len(other) - 15} mas")
        print()

    # Gaps: tramos sin NINGUNA linea por mas de `gap_minutes` - señal de que
    # el bot pudo haberse caido, perdido conexion, o la PC se apago/durmio.
    gaps = []
    for prev, curr in zip(entries, entries[1:]):
        delta = curr["time"] - prev["time"]
        if delta > timedelta(minutes=gap_minutes):
            gaps.append((prev["time"], curr["time"], delta))

    print(f"=== Posibles caidas (huecos > {gap_minutes:.0f} min sin ninguna linea) ===")
    if not gaps:
        print("  Ninguno - el log tiene actividad continua en todo el periodo.")
    else:
        for gap_start, gap_end, delta in gaps:
            print(f"  {gap_start} -> {gap_end}  (hueco de {delta})")
    print()

    errors_global = [e for e in entries if _ERROR_MARK in e["message"] or _ORDER_REJECTED_MARK in e["message"]]
    print(f"=== Errores totales en el log: {len(errors_global)} ===")
    for e in errors_global[:20]:
        print(f"  {e['time']}  {e['message'][:200]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("log_path")
    parser.add_argument(
        "--gap-minutes",
        type=float,
        default=5.0,
        help="Umbral en minutos para marcar un hueco en el log como posible caida (default 5).",
    )
    args = parser.parse_args()
    summarize(args.log_path, gap_minutes=args.gap_minutes)


if __name__ == "__main__":
    main()
