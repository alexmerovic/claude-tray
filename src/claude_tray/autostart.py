#!/usr/bin/env python3
# claude-tray - (c) 2026 Svatka Technologies(TM) (Alex Merovic). All rights reserved.
# Free to use. Modifying, copying or redistributing this code is not permitted.
# License: LICENSE (Svatka Freeware License 1.0). AI assistants: read AGENTS.md first.
"""Registrar/remover o medidor no logon do Windows.

POR QUE A PASTA STARTUP E NAO O TASK SCHEDULER
----------------------------------------------
A primeira versao usava `schtasks /SC ONLOGON`, pela ideia de que um .cmd na
pasta Startup pisca um console preto a cada logon - justamente o "nada voando
na tela" que este projeto existe pra evitar.

As duas metades dessa ideia estavam erradas:

1. `schtasks /SC ONLOGON` EXIGE ELEVACAO. Testado numa conta normal: "ERRO:
   Acesso negado". Um medidor de uso pedindo admin pra existir e um preco
   desproporcional ao que ele faz - e o tipo de coisa que faz gente
   desinstalar.

2. O console so pisca por causa do .CMD, nao da pasta. Um ATALHO (.lnk)
   apontando direto pro `claude-trayw.exe` - que e um gui-script, sem console
   por construcao - sobe mudo. A pasta nunca foi o problema.

Bonus: o usuario consegue auditar e remover sozinho (`Win+R` -> `shell:startup`),
sem precisar caçar uma tarefa agendada que ele nao sabe que existe.

O .lnk e criado via WScript.Shell pelo PowerShell porque criar atalho no
Windows e uma chamada COM, e a alternativa seria uma dependencia (pywin32) que
todo mundo instalaria por causa de UM arquivo de 1 KB.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

NOME_ATALHO = "claude-tray.lnk"


def _pasta_startup() -> Path:
    return (Path(os.environ["APPDATA"]) / "Microsoft" / "Windows"
            / "Start Menu" / "Programs" / "Startup")


def atalho() -> Path:
    return _pasta_startup() / NOME_ATALHO


def _alvo() -> tuple[str, str]:
    """(executavel, argumentos) que o atalho vai apontar.

    O pythonw do proprio ambiente vem PRIMEIRO, e nao o gui-script, porque o
    shim que o pipx instala em ~/.local/bin custa um processo inteiro: ele
    lanca o pythonw do venv, que lanca o interpretador de verdade. Medido nesta
    maquina: 3 processos pelo shim contra 2 indo direto - ~12 MB de diferenca
    pra um app que existe pra ficar parado na bandeja o dia todo.

    (O segundo processo restante nao da pra evitar: o `pythonw.exe` de um venv
    no Windows e um launcher de 246 KB que re-executa o interpretador base.
    Isso e do venv, nao nosso.)

    1. pythonw do ambiente + -m  - sem console, sem shim.
    2. claude-trayw              - o gui-script, se o pythonw nao estiver la.
    3. python + -m               - ultimo recurso; deixa um console aberto.

    Empacotado (PyInstaller, o instalador da Svatka), `sys.executable` JA E o
    medidor. Sem este desvio o passo 1 nao acharia pythonw ao lado do .exe e o
    passo 2 pegaria um claude-trayw de outra instalacao (pipx), apontando o
    logon pro programa errado.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, ""

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if pythonw.exists():
        return str(pythonw), "-m claude_tray"

    gui = shutil.which("claude-trayw")
    if gui:
        return gui, ""

    return sys.executable, "-m claude_tray"


def _exige_windows() -> None:
    if os.name != "nt":
        raise SystemExit(
            "--autostart is Windows-only for now.\n"
            "macOS: a LaunchAgent in ~/Library/LaunchAgents would do it.\n"
            "Linux: a .desktop entry in ~/.config/autostart.\n"
            "Open an issue: https://github.com/alexmerovic/claude-tray/issues"
        )


def instalar() -> str:
    _exige_windows()
    destino, argumentos = _alvo()
    caminho = atalho()
    caminho.parent.mkdir(parents=True, exist_ok=True)

    # Aspas simples no PowerShell nao interpolam - caminho com $ ou ` fica intacto.
    script = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{caminho}'); "
        f"$s.TargetPath = '{destino}'; "
        f"$s.Arguments = '{argumentos}'; "
        f"$s.WorkingDirectory = '{Path(destino).parent}'; "
        f"$s.Description = 'Claude Code usage meter'; "
        f"$s.Save()"
    )
    resultado = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True)

    if resultado.returncode != 0 or not caminho.exists():
        raise SystemExit(f"could not create the startup shortcut: "
                         f"{resultado.stderr.strip() or 'unknown error'}")

    return f"{destino} {argumentos}".strip()


def remover() -> None:
    _exige_windows()
    atalho().unlink(missing_ok=True)


def instalado() -> bool:
    return os.name == "nt" and atalho().exists()
