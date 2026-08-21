#!/usr/bin/env python3
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

    pid = processo.rodando()
    leitura = usage_api.ler() if rede else {"ok": False, "motivo": "offline"}
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
        "pct": round(float(leitura.get("pct") or 0.0)),
        "pct_week": round(float(leitura.get("pct_semana") or 0.0)),
    }


def _imprimir_status(dados: dict) -> None:
    print(f"meter        {'running (pid ' + str(dados['pid']) + ')' if dados['running'] else 'stopped'}")
    print(f"autostart    {'registered' if dados['autostart'] else 'not registered'}")
    print(f"config       {dados['config']}")
    if dados["reading_ok"]:
        print(f"5h window    {dados['pct']}%   (source: {dados['source']})")
        print(f"week         {dados['pct_week']}%")
    else:
        print(f"reading      unavailable ({dados['reason']})")


def main(argv: list[str] | None = None) -> int:
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
        print(f"Scheduled task {autostart.NOME_TAREFA} removed.")
        return 0

    if args.autostart:
        alvo = autostart.instalar()
        print(f"Scheduled task {autostart.NOME_TAREFA} registered at logon:\n  {alvo}")
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
