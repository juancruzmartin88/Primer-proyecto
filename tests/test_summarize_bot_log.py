from scripts.summarize_bot_log import summarize

_SAMPLE = """\
2026-09-22 14:50:53.039 | INFO     | __main__:run:66 - Arrancando bot | dry_run=False | simbolos=['BTCUSDm', 'XAUUSDm'] | timeframe=H1 | riesgo_por_operacion=2.0%
2026-09-22 14:50:55.214 | INFO     | src.mt5_client:connect:104 - Conectado a MT5: servidor=Exness-MT5Real11 login=478026672
2026-09-22 14:50:55.214 | INFO     | __main__:run:78 - XAUUSDm: el bot descarta automaticamente cualquier señal cuyo Stop Loss tecnico, al lote minimo del broker, fuerce mas del 2.0% de riesgo real sobre el balance
2026-09-23 09:38:09.146 | WARNING  | __main__:run:92 - Operacion bloqueada por gestion de riesgo (XAUUSDm): Ya hay 1 posiciones abiertas para este instrumento, el limite configurado es 1.
2026-09-23 09:38:39.195 | WARNING  | __main__:run:92 - Operacion bloqueada por gestion de riesgo (XAUUSDm): Ya hay 1 posiciones abiertas para este instrumento, el limite configurado es 1.
2026-09-23 09:40:00.000 | INFO     | __main__:iterate:175 - [DRY_RUN] Se simularia orden: BTCUSDm BUY 0.01
"""


def _section(out: str, symbol: str) -> str:
    start = out.index(f"=== {symbol} ===")
    end = out.index("\n=== ", start + 1)
    return out[start:end]


def test_summarize_excludes_boot_banner_from_symbol_activity(tmp_path, capsys):
    log_path = tmp_path / "bot.log"
    log_path.write_text(_SAMPLE)

    summarize(str(log_path))

    out = capsys.readouterr().out
    assert "Arranques del bot detectados: 1" in out

    btc_section = _section(out, "BTCUSDm")
    # La orden real de BTC aparece como actividad, no como "sin nada".
    assert "[DRY_RUN]" in btc_section
    assert "Sin ninguna señal" not in btc_section

    xau_section = _section(out, "XAUUSDm")
    assert "x2" in xau_section  # 2 bloqueos de Oro agrupados
    # El aviso de arranque de Oro (seccion 3.2) no cuenta como bloqueo.
    assert "x1" not in xau_section

    eth_section = _section(out, "ETHUSDm")
    assert "Sin ninguna señal" in eth_section


def test_summarize_handles_missing_log_gracefully(tmp_path, capsys):
    log_path = tmp_path / "empty.log"
    log_path.write_text("linea sin formato reconocido\n")

    summarize(str(log_path))

    out = capsys.readouterr().out
    assert "No se pudo parsear ninguna linea" in out
