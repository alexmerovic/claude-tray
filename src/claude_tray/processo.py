#!/usr/bin/env python3
"""Instancia unica: um PID em disco e a pergunta "esse processo ainda vive?".

POR QUE NAO os.kill(pid, 0)
---------------------------
No POSIX o sinal 0 e a forma canonica de perguntar "existe?". No WINDOWS a
mesma chamada NAO pergunta nada: os.kill despacha pra TerminateProcess e MATA
o processo. Num app cuja unica funcao e ficar vivo na bandeja, o teste de
vitalidade nao pode ser a causa da morte. Aqui o caminho Windows usa
OpenProcess + WaitForSingleObject, que so observam.
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import DIR_CONFIG

PID_PATH = DIR_CONFIG / "tray.pid"

_SYNCHRONIZE = 0x00100000
_WAIT_TIMEOUT = 0x00000102          # ainda sinalizando = ainda rodando


def _vivo(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(_SYNCHRONIZE, False, pid)
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == _WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True        # existe, so nao e nosso. Existir e o que importa.
    return True


def rodando() -> int | None:
    """PID do medidor em execucao, ou None. PID orfao e limpo na passagem."""
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if _vivo(pid):
        return pid
    PID_PATH.unlink(missing_ok=True)        # sobrou de um crash; nao vale nada
    return None


def registrar() -> None:
    DIR_CONFIG.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")


def liberar() -> None:
    PID_PATH.unlink(missing_ok=True)
