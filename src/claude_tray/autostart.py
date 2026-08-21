#!/usr/bin/env python3
"""Registrar/remover o medidor no logon do Windows.

POR QUE TASK SCHEDULER E NAO A PASTA STARTUP
--------------------------------------------
Um .cmd na pasta Startup pisca um console preto na cara do usuario a cada
logon - justamente o "nada voando na tela" que este projeto existe pra evitar.
A tarefa agendada aponta direto pro launcher GUI (claude-trayw.exe, sem
console) e sobe muda.

COMO O ALVO E DESCOBERTO, EM ORDEM
----------------------------------
1. claude-trayw   - o gui-script que o pyproject instala. Sem console.
2. pythonw -m     - quem clonou o repo em vez de instalar o pacote.
3. python -m      - ultimo recurso; funciona, mas deixa um console aberto.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

NOME_TAREFA = "ClaudeTray"


def _alvo() -> str:
    """Linha de comando que o agendador vai executar, ja com aspas."""
    gui = shutil.which("claude-trayw")
    if gui:
        return f'"{gui}"'

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    executavel = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{executavel}" -m claude_tray'


def _exige_windows() -> None:
    if os.name != "nt":
        raise SystemExit(
            "--autostart is Windows-only for now.\n"
            "macOS: a LaunchAgent in ~/Library/LaunchAgents would do it.\n"
            "Linux: a .desktop entry in ~/.config/autostart.\n"
            "PRs welcome."
        )


def instalar() -> str:
    _exige_windows()
    comando = [
        "schtasks", "/Create",
        "/TN", NOME_TAREFA,
        "/SC", "ONLOGON",
        "/TR", _alvo(),
        "/RL", "LIMITED",       # menor privilegio: o medidor so faz um GET
        "/F",                   # sobrescreve registro anterior
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise SystemExit(f"schtasks failed: {resultado.stderr.strip()}")
    return _alvo()


def remover() -> None:
    _exige_windows()
    subprocess.run(["schtasks", "/Delete", "/TN", NOME_TAREFA, "/F"],
                   capture_output=True, text=True)


def instalado() -> bool:
    if os.name != "nt":
        return False
    resultado = subprocess.run(["schtasks", "/Query", "/TN", NOME_TAREFA],
                               capture_output=True, text=True)
    return resultado.returncode == 0
