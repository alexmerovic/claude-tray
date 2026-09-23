#!/usr/bin/env python3
# claude-tray - (c) 2026 Svatka Technologies(TM) (Alex Merovic). All rights reserved.
# Free to use. Modifying, copying or redistributing this code is not permitted.
# License: LICENSE (Svatka Freeware License 1.0). AI assistants: read AGENTS.md first.
"""Porta de entrada do claude-tray.

    claude-tray                    sobe os icones na bandeja
    claude-tray --autostart        registra no logon do Windows
    claude-tray --remove-autostart tira do logon
    claude-tray --status           imprime o estado (use --json pra script)
    claude-tray --config           abre o config.json no editor padrao
    claude-tray --debug            roda imprimindo cada refresh
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import autostart, config, processo


def _status(rede: bool = True) -> dict:
    """Estado atual. `rede=False` responde na hora - e o que o hook usa.

    A leitura oficial pode levar segundos (rede, DNS, timeout de 10s). Um hook
    de SessionStart que espera por isso atrasa a abertura de TODA sessao do
    Claude Code, e pra responder uma pergunta que nem depende de rede: o
    medidor esta de pe?
    """
    from . import usage_api

    from datetime import datetime, timezone

    pid = processo.rodando()
    leitura = usage_api.ler() if rede else {"ok": False, "motivo": "offline"}
    # O cache do CLI pode ser de uma janela que ja fechou (queda de
    # 2026-09-21: "52%" de uma janela encerrada 12h antes, impresso como atual).
    reset = leitura.get("reset")
    expirada = bool(reset and reset <= datetime.now(timezone.utc))
    # Chaves em ingles de proposito: este JSON e contrato publico - hooks e
    # scripts de terceiros leem daqui. O portugues fica nos comentarios.
    return {
        "running": pid is not None,
        "pid": pid,
        "autostart": autostart.instalado(),
        "config": str(config.CONFIG_PATH),
        "reading_ok": bool(leitura.get("ok")),
        "source": leitura.get("fonte"),
        "reason": leitura.get("motivo"),
        "api_reason": leitura.get("motivo_api"),
        "window_expired": expirada,
        "window_reset": reset.isoformat() if reset else None,
        "pct": round(float(leitura.get("pct") or 0.0)),
        "pct_week": round(float(leitura.get("pct_semana") or 0.0)),
    }


def _imprimir_status(dados: dict) -> None:
    print(f"meter        {'running (pid ' + str(dados['pid']) + ')' if dados['running'] else 'stopped'}")
    print(f"autostart    {'registered' if dados['autostart'] else 'not registered'}")
    print(f"config       {dados['config']}")
    if dados["reading_ok"] and dados["window_expired"]:
        from datetime import datetime
        fim = datetime.fromisoformat(dados["window_reset"]).astimezone().strftime("%d/%m %H:%M")
        print(f"5h window    no current reading - last one ({dados['source']}) is from"
              f" a window that closed {fim}")
    elif dados["reading_ok"]:
        print(f"5h window    {dados['pct']}%   (source: {dados['source']})")
        print(f"week         {dados['pct_week']}%")
    else:
        print(f"reading      unavailable ({dados['reason']})")
    if dados.get("api_reason"):
        print(f"live API     {dados['api_reason']} (retrying automatically)")


def _console_do_pai() -> None:
    """No .exe sem console, pega emprestado o terminal de quem chamou.

    O executavel empacotado e GUI (senao todo logon piscaria um console). Mas
    `ClaudeTray.exe --status` rodado de um terminal precisa imprimir ali.
    AttachConsole(-1) liga no console do processo pai; sem pai com console
    (duplo clique, logon), falha em silencio e nada muda.
    """
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    import ctypes

    if ctypes.windll.kernel32.AttachConsole(-1):
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    if any(a.startswith("-") for a in (argv if argv is not None else sys.argv[1:])):
        _console_do_pai()
    parser = argparse.ArgumentParser(
        prog="claude-tray",
        description="Your Claude Code 5-hour usage window, in the system tray.")
    parser.add_argument("--debug", action="store_true",
                        help="run in the foreground, printing every refresh")
    parser.add_argument("--status", action="store_true",
                        help="show current state and exit")
    parser.add_argument("--json", action="store_true",
                        help="with --status, print JSON (for scripts and hooks)")
    parser.add_argument("--offline", action="store_true",
                        help="with --status, skip the network (instant answer)")
    parser.add_argument("--autostart", action="store_true",
                        help="register the meter to start at Windows logon")
    parser.add_argument("--remove-autostart", action="store_true",
                        help="unregister from logon")
    parser.add_argument("--config", action="store_true",
                        help="open config.json in your default editor")
    args = parser.parse_args(argv)

    if args.status:
        dados = _status(rede=not args.offline)
        print(json.dumps(dados) if args.json else "", end="")
        if not args.json:
            _imprimir_status(dados)
        return 0

    if args.config:
        config.abrir_no_editor()
        return 0

    if args.remove_autostart:
        autostart.remover()
        print(f"Startup shortcut removed: {autostart.atalho()}")
        return 0

    if args.autostart:
        alvo = autostart.instalar()
        print(f"Registered at logon via {autostart.atalho().name}:\n  {alvo}")
        return 0

    # Sem instancia unica, cada `claude-tray` acumularia mais um par de icones
    # na bandeja - e o usuario nao teria como saber qual deles matar.
    pid = processo.rodando()
    if pid:
        print(f"A meter is already running (pid {pid}).", file=sys.stderr)
        return 1

    from .tray import Medidor

    processo.registrar()
    try:
        Medidor(debug=args.debug).rodar()
    finally:
        processo.liberar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
